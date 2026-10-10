"""Network-layer action interceptor and HTTP egress proxy filter."""

from __future__ import annotations

import re
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


class NetworkInterceptor:
    """Evaluates outbound HTTP requests and blocks unauthorized irreversible mutations at the network boundary."""

    BLOCKED_DESTINATIONS = [
        r".*api\.stripe\.com/v1/charges.*",
        r".*api\.stripe\.com/v1/payment_intents.*",
        r".*paypal\.com/.*/checkout.*",
        r".*/api/v[0-9]+/orders/confirm.*",
        r".*/api/v[0-9]+/checkout/complete.*",
        r".*/api/v[0-9]+/transfers.*",
        r".*/api/v[0-9]+/admin/terminate.*",
    ]

    def __init__(self, classifier: Optional[ActionTierClassifier] = None) -> None:
        self.classifier = classifier or ActionTierClassifier()

    def evaluate_request(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        body: Optional[Any] = None,
    ) -> InterceptionDecision:
        """Evaluate outbound HTTP request before dispatch."""
        action = ActionPayload(
            category=ActionCategory.HTTP_MUTATE if method.upper() not in ("GET", "HEAD") else ActionCategory.HTTP_READ,
            target=url,
            parameters={"method": method.upper(), "body": body},
            metadata={"headers": headers or {}},
        )
        tier = self.classifier.classify(action)

        # Check explicit blocked URL patterns
        for pat in self.BLOCKED_DESTINATIONS:
            if re.search(pat, url, re.IGNORECASE):
                tier = ActionTier.TIER_3_IRREVERSIBLE_COMMIT
                break

        if tier == ActionTier.TIER_3_IRREVERSIBLE_COMMIT:
            return InterceptionDecision(
                action_id=action.action_id,
                tier=tier,
                layer=InterceptionLayer.NETWORK,
                decision=GatingDecisionType.BLOCKED,
                reason=f"Blocked irreversible HTTP {method.upper()} to '{url}'",
                rule_matched="network_commit_endpoint_rule",
            )

        decision_type = (
            GatingDecisionType.MONITORED
            if tier == ActionTier.TIER_2_MUTATING
            else GatingDecisionType.PERMITTED
        )

        return InterceptionDecision(
            action_id=action.action_id,
            tier=tier,
            layer=InterceptionLayer.NETWORK,
            decision=decision_type,
            reason=f"HTTP request allowed: {method.upper()} {url}",
        )
