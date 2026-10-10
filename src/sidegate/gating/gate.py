"""Runtime Irreversible Action Gate coordinating multi-layer defense policies."""

from __future__ import annotations

import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field

from sidegate.core.models import (
    ActionPayload,
    ActionTier,
    GatingDecisionType,
    InterceptionDecision,
    InterceptionEvent,
    InterceptionLayer,
)
from sidegate.gating.classifier import ActionTierClassifier
from sidegate.gating.dom_interceptor import DOMInterceptor
from sidegate.gating.harness_interceptor import HarnessInterceptor
from sidegate.gating.network_interceptor import NetworkInterceptor


class GatingPolicy(BaseModel):
    """Configuration policy governing the Irreversible Action Gate."""

    policy_id: str = Field(default_factory=lambda: f"pol-{uuid.uuid4().hex[:8]}")
    mode: str = Field(
        default="ENFORCE",
        description="Operating mode: ENFORCE (raise/block), AUDIT (log only), SIMULATE (dry-run)",
    )
    block_tier3: bool = True
    require_confirmation_for_tier3: bool = True
    allowed_overrides: List[str] = Field(default_factory=list)
    monitored_domains: List[str] = Field(
        default_factory=lambda: ["dom", "database", "filesystem", "network"]
    )


class RuntimeActionGate:
    """Enterprise coordinator for multi-layer action gating across Harness, DOM, and Network tiers."""

    def __init__(
        self,
        policy: Optional[GatingPolicy] = None,
        on_event: Optional[Callable[[InterceptionEvent], None]] = None,
    ) -> None:
        self.policy = policy or GatingPolicy()
        self.classifier = ActionTierClassifier()
        self.harness = HarnessInterceptor(
            classifier=self.classifier,
            enforce_block=(self.policy.mode == "ENFORCE"),
            on_event=self._record_event,
        )
        self.dom = DOMInterceptor(classifier=self.classifier)
        self.network = NetworkInterceptor(classifier=self.classifier)
        self.on_event = on_event
        self.events: List[InterceptionEvent] = []
        self._tokens: Dict[str, float] = {}

    def _record_event(self, event: InterceptionEvent) -> None:
        self.events.append(event)
        if self.on_event:
            self.on_event(event)

    def issue_confirmation_token(self, action_id: str) -> str:
        """Issue a temporary cryptographically random authorization token for human-approved commits."""
        token = f"CONFIRMED-{action_id}-{uuid.uuid4().hex[:12]}"
        self._tokens[token] = time.time()
        return token

    def is_token_valid(self, token: str) -> bool:
        """Check if an authorization token is valid and unexpired (TTL: 300s)."""
        if token not in self._tokens:
            return False
        issued_at = self._tokens[token]
        return (time.time() - issued_at) < 300.0

    def evaluate_action(
        self,
        action: ActionPayload,
        confirmation_token: Optional[str] = None,
        active_invariants: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> InterceptionDecision:
        """Evaluate an action through the runtime harness interceptor."""
        valid_token = None
        if confirmation_token and self.is_token_valid(confirmation_token):
            valid_token = confirmation_token

        return self.harness.intercept(
            action=action,
            confirmation_token=valid_token,
            active_invariants=active_invariants,
            context=context,
        )

    def evaluate_dom_click(
        self,
        target_selector: str,
        element_text: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> InterceptionDecision:
        """Evaluate a DOM click interaction through the DOM interceptor."""
        decision = self.dom.evaluate_click(target_selector, element_text, attributes)
        # Log event
        action = ActionPayload(
            tier=decision.tier,
            target=target_selector,
            parameters={"text": element_text or ""},
            metadata=attributes or {},
        )
        event = InterceptionEvent(action=action, decision=decision)
        self._record_event(event)
        return decision

    def evaluate_network_request(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        body: Optional[Any] = None,
    ) -> InterceptionDecision:
        """Evaluate an outbound HTTP request through the network interceptor."""
        decision = self.network.evaluate_request(url, method, headers, body)
        action = ActionPayload(
            tier=decision.tier,
            target=url,
            parameters={"method": method, "body": body},
            metadata={"headers": headers or {}},
        )
        event = InterceptionEvent(action=action, decision=decision)
        self._record_event(event)
        return decision

    def get_telemetry_stats(self) -> Dict[str, Any]:
        """Aggregate real-time interception statistics."""
        total = len(self.events)
        blocked = sum(1 for e in self.events if e.decision.decision == GatingDecisionType.BLOCKED)
        monitored = sum(1 for e in self.events if e.decision.decision == GatingDecisionType.MONITORED)
        permitted = sum(1 for e in self.events if e.decision.decision == GatingDecisionType.PERMITTED)

        layer_counts = {
            InterceptionLayer.HARNESS.value: sum(
                1 for e in self.events if e.decision.layer == InterceptionLayer.HARNESS
            ),
            InterceptionLayer.DOM.value: sum(
                1 for e in self.events if e.decision.layer == InterceptionLayer.DOM
            ),
            InterceptionLayer.NETWORK.value: sum(
                1 for e in self.events if e.decision.layer == InterceptionLayer.NETWORK
            ),
        }

        tier_counts = {
            f"Tier {t.value}": sum(1 for e in self.events if e.action.tier == t)
            for t in ActionTier
        }

        return {
            "total_intercepted": total,
            "blocked": blocked,
            "monitored": monitored,
            "permitted": permitted,
            "block_rate": (blocked / total) if total > 0 else 0.0,
            "layers": layer_counts,
            "tiers": tier_counts,
            "mode": self.policy.mode,
        }
