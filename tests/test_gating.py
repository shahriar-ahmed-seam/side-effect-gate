"""Unit and integration tests for the multi-tier Irreversible Action Gate."""

from __future__ import annotations

import pytest

from sidegate.core.exceptions import IrreversibleActionBlockedError
from sidegate.core.models import (
    ActionCategory,
    ActionPayload,
    ActionTier,
    GatingDecisionType,
    InterceptionLayer,
)
from sidegate.gating.classifier import ActionTierClassifier
from sidegate.gating.dom_interceptor import DOMInterceptor
from sidegate.gating.gate import GatingPolicy, RuntimeActionGate
from sidegate.gating.harness_interceptor import HarnessInterceptor
from sidegate.gating.network_interceptor import NetworkInterceptor


def test_action_tier_classifier_dom():
    classifier = ActionTierClassifier()

    # Commit clicks (Tier 3)
    checkout_action = ActionPayload(
        category=ActionCategory.UI_CLICK,
        target="button#checkout",
        parameters={"text": "Complete Purchase Now"},
    )
    assert classifier.classify(checkout_action) == ActionTier.TIER_3_IRREVERSIBLE_COMMIT

    pay_action = ActionPayload(
        category=ActionCategory.UI_CLICK,
        target=".btn-payment",
        metadata={"aria-label": "Pay $149.99"},
    )
    assert classifier.classify(pay_action) == ActionTier.TIER_3_IRREVERSIBLE_COMMIT

    # Mutating clicks (Tier 2)
    cart_action = ActionPayload(
        category=ActionCategory.UI_CLICK,
        target="button.add-to-cart",
        parameters={"text": "Add to Cart"},
    )
    assert classifier.classify(cart_action) == ActionTier.TIER_2_MUTATING

    # Navigation clicks (Tier 0)
    nav_action = ActionPayload(
        category=ActionCategory.UI_CLICK,
        target="a.nav-item-electronics",
        parameters={"text": "View Electronics"},
    )
    assert classifier.classify(nav_action) == ActionTier.TIER_0_READ_ONLY


def test_action_tier_classifier_shell_and_http():
    classifier = ActionTierClassifier()

    # Destructive shell command (Tier 3)
    rm_action = ActionPayload(
        category=ActionCategory.SHELL_COMMAND,
        target="rm -rf /var/data/prod",
    )
    assert classifier.classify(rm_action) == ActionTier.TIER_3_IRREVERSIBLE_COMMIT

    # Read-only shell command (Tier 0)
    ls_action = ActionPayload(
        category=ActionCategory.SHELL_COMMAND,
        target="ls -la /tmp",
    )
    assert classifier.classify(ls_action) == ActionTier.TIER_0_READ_ONLY

    # HTTP Checkout (Tier 3)
    http_post_checkout = ActionPayload(
        category=ActionCategory.HTTP_MUTATE,
        target="https://api.store.com/v1/checkout/complete",
        parameters={"method": "POST"},
    )
    assert classifier.classify(http_post_checkout) == ActionTier.TIER_3_IRREVERSIBLE_COMMIT

    # HTTP Catalog Read (Tier 0)
    http_get = ActionPayload(
        category=ActionCategory.HTTP_READ,
        target="https://api.store.com/v1/items",
        parameters={"method": "GET"},
    )
    assert classifier.classify(http_get) == ActionTier.TIER_0_READ_ONLY


def test_dom_interceptor_and_script():
    interceptor = DOMInterceptor()

    decision_blocked = interceptor.evaluate_click(
        target_selector="button#submit-order",
        element_text="Submit Order",
    )
    assert decision_blocked.decision == GatingDecisionType.BLOCKED
    assert decision_blocked.layer == InterceptionLayer.DOM

    decision_allowed = interceptor.evaluate_click(
        target_selector="button.filter-price",
        element_text="Filter under $50",
    )
    assert decision_allowed.decision in (GatingDecisionType.PERMITTED, GatingDecisionType.MONITORED)

    script = DOMInterceptor.generate_anti_checkout_script()
    assert "window.__SIDEGATE_GUARD_INITIALIZED__" in script
    assert "event.stopImmediatePropagation()" in script


def test_network_interceptor():
    interceptor = NetworkInterceptor()

    decision_blocked = interceptor.evaluate_request(
        url="https://api.stripe.com/v1/charges",
        method="POST",
        body={"amount": 2000, "currency": "usd"},
    )
    assert decision_blocked.decision == GatingDecisionType.BLOCKED
    assert decision_blocked.layer == InterceptionLayer.NETWORK

    decision_allowed = interceptor.evaluate_request(
        url="https://api.store.com/products/search?q=laptop",
        method="GET",
    )
    assert decision_allowed.decision == GatingDecisionType.PERMITTED


def test_harness_interceptor_enforcement():
    interceptor = HarnessInterceptor(enforce_block=True)

    tier3_action = ActionPayload(
        category=ActionCategory.UI_CLICK,
        target="button#checkout",
        parameters={"text": "Place Order"},
    )

    # Must raise IrreversibleActionBlockedError without token
    with pytest.raises(IrreversibleActionBlockedError) as exc_info:
        interceptor.intercept(tier3_action)
    assert "Blocked unconfirmed Tier-3" in str(exc_info.value)

    # With valid confirmation token, action should be permitted
    decision = interceptor.intercept(tier3_action, confirmation_token="CONFIRMED-act-123")
    assert decision.decision == GatingDecisionType.PERMITTED


def test_runtime_action_gate_full_lifecycle():
    gate = RuntimeActionGate(policy=GatingPolicy(mode="ENFORCE"))

    # Test DOM evaluation
    dom_dec = gate.evaluate_dom_click("button#pay-button", "Pay Now")
    assert dom_dec.decision == GatingDecisionType.BLOCKED

    # Test Network evaluation
    net_dec = gate.evaluate_network_request("https://api.store.com/orders/confirm", "POST")
    assert net_dec.decision == GatingDecisionType.BLOCKED

    # Test confirmation token generation & bypass
    action_id = "act-test-001"
    token = gate.issue_confirmation_token(action_id)
    assert gate.is_token_valid(token)

    harness_act = ActionPayload(
        action_id=action_id,
        category=ActionCategory.UI_CLICK,
        target="button#checkout",
        parameters={"text": "Checkout"},
    )
    approved_dec = gate.evaluate_action(harness_act, confirmation_token=token)
    assert approved_dec.decision == GatingDecisionType.PERMITTED

    # Check telemetry stats aggregation
    stats = gate.get_telemetry_stats()
    assert stats["total_intercepted"] == 3
    assert stats["blocked"] == 2
    assert stats["permitted"] == 1
    assert stats["layers"]["DOM"] == 1
    assert stats["layers"]["NETWORK"] == 1
    assert stats["layers"]["HARNESS"] == 1
