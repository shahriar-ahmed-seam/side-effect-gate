"""Playwright browser automation adapter with DOM and network interception hooks."""

from __future__ import annotations

from typing import Any, Dict, Optional

from sidegate.core.models import GatingDecisionType, InterceptionDecision
from sidegate.gating.dom_interceptor import DOMInterceptor
from sidegate.gating.gate import RuntimeActionGate


class PlaywrightGateAdapter:
    """Drop-in integration adapter for Playwright browser automation instances."""

    def __init__(self, gate: Optional[RuntimeActionGate] = None) -> None:
        self.gate = gate or RuntimeActionGate()

    def get_guard_init_script(self) -> str:
        """Retrieve client-side DOM anti-checkout script to inject into Playwright page."""
        return DOMInterceptor.generate_anti_checkout_script()

    def check_click(
        self,
        selector: str,
        text: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> InterceptionDecision:
        """Validate click interaction before invoking page.click(selector)."""
        return self.gate.evaluate_dom_click(
            target_selector=selector,
            element_text=text,
            attributes=attributes,
        )

    def check_network_route(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        post_data: Optional[Any] = None,
    ) -> InterceptionDecision:
        """Evaluate network request before Playwright route.continue_() or route.abort()."""
        return self.gate.evaluate_network_request(
            url=url,
            method=method,
            headers=headers,
            body=post_data,
        )

    def should_abort_route(
        self,
        url: str,
        method: str = "GET",
    ) -> bool:
        """Quick boolean helper returning True if request must be aborted at network layer."""
        dec = self.check_network_route(url, method)
        return dec.decision == GatingDecisionType.BLOCKED
