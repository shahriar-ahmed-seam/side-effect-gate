"""Unit tests for SideGate ecosystem adapters (Anthropic, Playwright, OpenAI)."""

from __future__ import annotations

import json

from sidegate.adapters.anthropic_adapter import AnthropicComputerUseAdapter
from sidegate.adapters.openai_adapter import OpenAIToolGateAdapter
from sidegate.adapters.playwright_adapter import PlaywrightGateAdapter
from sidegate.core.models import GatingDecisionType
from sidegate.gating.gate import RuntimeActionGate


def test_anthropic_computer_use_adapter():
    gate = RuntimeActionGate()
    adapter = AnthropicComputerUseAdapter(
        gate=gate,
        tool_executor=lambda name, inp: f"Executed {name}",
    )

    # 1. Destructive bash command -> Blocked
    bash_blocked = adapter.intercept_and_execute(
        tool_name="bash",
        tool_input={"command": "rm -rf /var/data/prod"},
        tool_use_id="tu-001",
    )
    assert bash_blocked["blocked"] is True
    assert bash_blocked["is_error"] is True
    assert "BLOCKED" in bash_blocked["content"]

    # 2. Safe read bash command -> Permitted
    bash_safe = adapter.intercept_and_execute(
        tool_name="bash",
        tool_input={"command": "ls -la /tmp"},
        tool_use_id="tu-002",
    )
    assert bash_safe["blocked"] is False
    assert bash_safe["is_error"] is False
    assert "Executed bash" in bash_safe["content"]

    # 3. Computer tool click on commit keyword -> Blocked
    click_blocked = adapter.intercept_and_execute(
        tool_name="computer",
        tool_input={"action": "left_click", "text": "Pay Now $500", "coordinate": [450, 780]},
        tool_use_id="tu-003",
    )
    assert click_blocked["blocked"] is True

    # 4. Computer tool click with valid confirmation token -> Permitted
    token = gate.issue_confirmation_token("tu-004")
    click_allowed = adapter.intercept_and_execute(
        tool_name="computer",
        tool_input={"action": "left_click", "text": "Pay Now $500", "coordinate": [450, 780]},
        tool_use_id="tu-004",
        confirmation_token=token,
    )
    assert click_allowed["blocked"] is False


def test_playwright_gate_adapter():
    adapter = PlaywrightGateAdapter()

    # Guard script
    script = adapter.get_guard_init_script()
    assert "window.__SIDEGATE_GUARD_INITIALIZED__" in script

    # Check DOM click
    click_dec = adapter.check_click("button#checkout", "Complete Order")
    assert click_dec.decision == GatingDecisionType.BLOCKED

    # Check network route
    assert adapter.should_abort_route("https://api.stripe.com/v1/charges", "POST") is True
    assert adapter.should_abort_route("https://api.store.com/products", "GET") is False


def test_openai_tool_gate_adapter():
    adapter = OpenAIToolGateAdapter(
        tool_dispatch_fn=lambda name, args: {"status": "ok", "result": 42}
    )

    # 1. Dangerous checkout tool -> Blocked
    res_blocked = adapter.intercept_and_dispatch(
        tool_name="execute_checkout_payment",
        arguments={"cart_id": "cart-123", "amount": 99.99},
        call_id="call-1",
    )
    assert res_blocked["blocked"] is True
    body = json.loads(res_blocked["content"])
    assert body["status"] == "BLOCKED"

    # 2. Safe query tool -> Permitted
    res_safe = adapter.intercept_and_dispatch(
        tool_name="get_product_catalog",
        arguments={"category": "electronics"},
        call_id="call-2",
    )
    assert res_safe["blocked"] is False
    body_safe = json.loads(res_safe["content"])
    assert body_safe["status"] == "ok"
