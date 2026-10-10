"""DOM-layer action interceptor and client-side guard script generator."""

from __future__ import annotations

from typing import Any, Dict, Optional

from sidegate.core.models import (
    ActionCategory,
    ActionPayload,
    ActionTier,
    GatingDecisionType,
    InterceptionDecision,
    InterceptionLayer,
)
from sidegate.gating.classifier import ActionTierClassifier


class DOMInterceptor:
    """Evaluates UI click interactions against DOM safety boundaries and generates browser guard scripts."""

    COMMIT_SELECTOR_PATTERNS = [
        r"button.*(checkout|pay|purchase|buy|order|confirm|transfer|delete|destroy).*",
        r"input\[type=['\"]submit['\"]\].*(checkout|pay|purchase|buy|order|confirm).*",
        r"a.*(checkout|finalize|wire-transfer).*",
        r"#checkout-btn",
        r"#pay-button",
        r".btn-checkout",
        r".btn-payment",
        r"[data-action=['\"](checkout|purchase|confirm-order)['\"]]",
    ]

    def __init__(self, classifier: Optional[ActionTierClassifier] = None) -> None:
        self.classifier = classifier or ActionTierClassifier()

    def evaluate_click(
        self,
        target_selector: str,
        element_text: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> InterceptionDecision:
        """Evaluate DOM click target before execution."""
        attrs = attributes or {}
        action = ActionPayload(
            category=ActionCategory.UI_CLICK,
            target=target_selector,
            parameters={"text": element_text or ""},
            metadata=attrs,
        )
        tier = self.classifier.classify(action)

        if tier == ActionTier.TIER_3_IRREVERSIBLE_COMMIT:
            return InterceptionDecision(
                action_id=action.action_id,
                tier=tier,
                layer=InterceptionLayer.DOM,
                decision=GatingDecisionType.BLOCKED,
                reason=f"Blocked irreversible DOM commit click on '{target_selector}' ('{element_text}')",
                rule_matched="dom_commit_interceptor_rule",
            )

        decision_type = (
            GatingDecisionType.MONITORED
            if tier == ActionTier.TIER_2_MUTATING
            else GatingDecisionType.PERMITTED
        )

        return InterceptionDecision(
            action_id=action.action_id,
            tier=tier,
            layer=InterceptionLayer.DOM,
            decision=decision_type,
            reason=f"DOM action classified as Tier {tier.value} ({tier.name})",
        )

    @classmethod
    def generate_anti_checkout_script(cls) -> str:
        """Generate client-side JavaScript guard script for injection into browser execution contexts.

        Intercepts click events at the capture phase, preventing DOM dispatch of irreversible commit clicks.
        """
        return """
(function() {
    if (window.__SIDEGATE_GUARD_INITIALIZED__) return;
    window.__SIDEGATE_GUARD_INITIALIZED__ = true;
    window.__SIDEGATE_INTERCEPTED_COMMITS__ = [];

    const COMMIT_KEYWORDS = [
        'checkout', 'pay now', 'pay', 'complete purchase', 'confirm order',
        'place order', 'submit order', 'wire transfer', 'send money',
        'delete account', 'destroy cluster', 'terminate'
    ];

    function isCommitElement(el) {
        if (!el || el.nodeType !== 1) return false;
        const text = (el.innerText || el.textContent || el.value || '').toLowerCase().trim();
        const aria = (el.getAttribute('aria-label') || '').toLowerCase().trim();
        const testStr = `${text} ${aria}`;

        for (const kw of COMMIT_KEYWORDS) {
            if (testStr.includes(kw)) return true;
        }

        const idClass = `${el.id || ''} ${el.className || ''}`.toLowerCase();
        if (idClass.includes('checkout') || idClass.includes('btn-pay') || idClass.includes('btn-checkout')) {
            return true;
        }

        return false;
    }

    document.addEventListener('click', function(event) {
        let target = event.target;
        let commitFound = false;

        while (target && target !== document.body) {
            if (isCommitElement(target)) {
                commitFound = true;
                break;
            }
            target = target.parentElement;
        }

        if (commitFound) {
            event.preventDefault();
            event.stopPropagation();
            event.stopImmediatePropagation();

            const record = {
                timestamp: Date.now(),
                tag: target.tagName,
                id: target.id,
                className: target.className,
                text: target.innerText || target.value,
                blocked: true
            };
            window.__SIDEGATE_INTERCEPTED_COMMITS__.push(record);
            console.warn('[SideGate:DOM] BLOCKED irreversible commit click:', record);
            window.dispatchEvent(new CustomEvent('SideGateCommitBlocked', { detail: record }));
            return false;
        }
    }, true);
})();
""".strip()
