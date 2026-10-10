"""Harness-layer action interceptor wrapping agent runtime execution boundaries."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from sidegate.core.exceptions import IrreversibleActionBlockedError
from sidegate.core.models import (
    ActionPayload,
    ActionTier,
    GatingDecisionType,
    InterceptionDecision,
    InterceptionEvent,
    InterceptionLayer,
)
from sidegate.gating.classifier import ActionTierClassifier


class HarnessInterceptor:
    """Intercepts agent execution commands at the host harness runtime level before dispatch."""

    def __init__(
        self,
        classifier: Optional[ActionTierClassifier] = None,
        enforce_block: bool = True,
        on_event: Optional[Callable[[InterceptionEvent], None]] = None,
    ) -> None:
        self.classifier = classifier or ActionTierClassifier()
        self.enforce_block = enforce_block
        self.on_event = on_event
        self.event_log: List[InterceptionEvent] = []

    def intercept(
        self,
        action: ActionPayload,
        confirmation_token: Optional[str] = None,
        active_invariants: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> InterceptionDecision:
        """Evaluate action payload and enforce gating decision."""
        tier = self.classifier.classify(action)
        action.tier = tier

        if tier == ActionTier.TIER_3_IRREVERSIBLE_COMMIT:
            if confirmation_token and confirmation_token.startswith("CONFIRMED-"):
                decision = InterceptionDecision(
                    action_id=action.action_id,
                    tier=tier,
                    layer=InterceptionLayer.HARNESS,
                    decision=GatingDecisionType.PERMITTED,
                    reason=f"Tier-3 action permitted with valid confirmation token '{confirmation_token}'",
                    confirmation_token=confirmation_token,
                )
            else:
                decision = InterceptionDecision(
                    action_id=action.action_id,
                    tier=tier,
                    layer=InterceptionLayer.HARNESS,
                    decision=GatingDecisionType.BLOCKED,
                    reason=f"Blocked unconfirmed Tier-3 irreversible commit: '{action.target}'",
                    rule_matched="harness_irreversible_action_policy",
                )
        elif tier == ActionTier.TIER_2_MUTATING:
            decision = InterceptionDecision(
                action_id=action.action_id,
                tier=tier,
                layer=InterceptionLayer.HARNESS,
                decision=GatingDecisionType.MONITORED,
                reason=f"Tier-2 mutating action permitted under continuous state-diff monitoring: '{action.target}'",
            )
        else:
            decision = InterceptionDecision(
                action_id=action.action_id,
                tier=tier,
                layer=InterceptionLayer.HARNESS,
                decision=GatingDecisionType.PERMITTED,
                reason=f"Tier-{tier.value} action permitted",
            )

        event = InterceptionEvent(
            action=action,
            decision=decision,
            active_invariants=active_invariants or [],
            context=context or {},
        )
        self.event_log.append(event)
        if self.on_event:
            self.on_event(event)

        if decision.decision == GatingDecisionType.BLOCKED and self.enforce_block:
            raise IrreversibleActionBlockedError(
                action_id=action.action_id,
                reason=decision.reason,
                layer=decision.layer.value,
            )

        return decision
