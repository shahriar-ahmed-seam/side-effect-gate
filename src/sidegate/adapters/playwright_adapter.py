"""Playwright browser automation adapter with DOM and network interception hooks."""

from __future__ import annotations

import inspect
from typing import Any, Dict, Optional, Set

from sidegate.core.exceptions import IrreversibleActionBlockedError
from sidegate.core.models import GatingDecisionType, InterceptionDecision
from sidegate.gating.dom_interceptor import DOMInterceptor
from sidegate.gating.gate import RuntimeActionGate


class PlaywrightGateAdapter:
    """Drop-in integration adapter for Playwright browser automation instances."""

    def __init__(self, gate: Optional[RuntimeActionGate] = None) -> None:
        self.gate = gate or RuntimeActionGate()
        self._attached_pages: Set[int] = set()

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

    async def attach_page(self, page: Any) -> None:
        """Asynchronously attach anti-checkout init script and network route interception to Playwright Page."""
        # 1. Inject DOM guard init script
        if hasattr(page, "add_init_script"):
            res = page.add_init_script(script=self.get_guard_init_script())
            if inspect.isawaitable(res):
                await res

        # 2. Setup network route filter
        if hasattr(page, "route"):
            async def _route_handler(route: Any) -> None:
                req = getattr(route, "request", None)
                url = req.url if req and hasattr(req, "url") else ""
                method = req.method if req and hasattr(req, "method") else "GET"

                if self.should_abort_route(url, method):
                    if hasattr(route, "abort"):
                        abort_res = route.abort("blockedbyclient")
                        if inspect.isawaitable(abort_res):
                            await abort_res
                else:
                    if hasattr(route, "continue_"):
                        cont_res = route.continue_()
                        if inspect.isawaitable(cont_res):
                            await cont_res

            route_res = page.route("**/*", _route_handler)
            if inspect.isawaitable(route_res):
                await route_res

        self._attached_pages.add(id(page))

    def attach_page_sync(self, page: Any) -> None:
        """Synchronously attach anti-checkout init script and network route interception to Playwright Page."""
        if hasattr(page, "add_init_script"):
            page.add_init_script(script=self.get_guard_init_script())

        if hasattr(page, "route"):
            def _sync_route_handler(route: Any) -> None:
                req = getattr(route, "request", None)
                url = req.url if req and hasattr(req, "url") else ""
                method = req.method if req and hasattr(req, "method") else "GET"

                if self.should_abort_route(url, method):
                    if hasattr(route, "abort"):
                        route.abort("blockedbyclient")
                else:
                    if hasattr(route, "continue_"):
                        route.continue_()

            page.route("**/*", _sync_route_handler)

        self._attached_pages.add(id(page))

    def is_attached(self, page: Any) -> bool:
        """Check if target page has been attached."""
        return id(page) in self._attached_pages

    async def safe_click(
        self,
        page: Any,
        selector: str,
        text: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
        confirmation_token: Optional[str] = None,
        **kwargs: Any,
    ) -> Any:
        """Validate click interaction with Action Gate before invoking page.click(selector)."""
        dec = self.check_click(selector, text=text, attributes=attributes)
        if dec.decision == GatingDecisionType.BLOCKED:
            if not confirmation_token or not self.gate.validate_token(confirmation_token):
                raise IrreversibleActionBlockedError(
                    action_id=dec.action_id,
                    reason=(
                        f"Blocked Tier-3 click on selector '{selector}' (text: '{text}'). "
                        f"Irreversible commit actions require explicit confirmation token."
                    ),
                    layer="DOM",
                )
        click_res = page.click(selector, **kwargs)
        if inspect.isawaitable(click_res):
            return await click_res
        return click_res

    def safe_click_sync(
        self,
        page: Any,
        selector: str,
        text: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
        confirmation_token: Optional[str] = None,
        **kwargs: Any,
    ) -> Any:
        """Synchronously validate click interaction with Action Gate before invoking page.click(selector)."""
        dec = self.check_click(selector, text=text, attributes=attributes)
        if dec.decision == GatingDecisionType.BLOCKED:
            if not confirmation_token or not self.gate.validate_token(confirmation_token):
                raise IrreversibleActionBlockedError(
                    action_id=dec.action_id,
                    reason=(
                        f"Blocked Tier-3 click on selector '{selector}' (text: '{text}'). "
                        f"Irreversible commit actions require explicit confirmation token."
                    ),
                    layer="DOM",
                )
        return page.click(selector, **kwargs)
