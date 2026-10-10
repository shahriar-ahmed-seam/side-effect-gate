"""Action tier classification engine based on pattern rules and semantic heuristics."""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from sidegate.core.models import ActionCategory, ActionPayload, ActionTier


class ActionTierClassifier:
    """Classifies computer-use agent actions into risk tiers T0, T1, T2, and T3."""

    # Keywords indicative of irreversible commit clicks in DOM
    DOM_COMMIT_KEYWORDS = [
        "checkout",
        "pay now",
        "pay",
        "complete purchase",
        "confirm order",
        "place order",
        "submit order",
        "wire transfer",
        "send money",
        "transfer funds",
        "delete account",
        "delete database",
        "destroy",
        "terminate cluster",
        "terminate instance",
        "drop table",
        "commit changes",
    ]

    DOM_COMMIT_SELECTORS = [
        r".*checkout.*",
        r".*pay.*btn.*",
        r".*btn-pay.*",
        r".*order-submit.*",
        r".*confirm-purchase.*",
        r".*btn-danger.*delete.*",
        r".*wire-transfer-submit.*",
        r".*finalize-payment.*",
    ]

    # Bash / Shell commands indicative of irreversible or destructive actions
    SHELL_TIER3_PATTERNS = [
        r"rm\s+(-[rfRF]+\s+|-[a-zA-Z]*[rR][a-zA-Z]*\s+).*",
        r"dropdb\s+.*",
        r"git\s+push\s+.*--force.*",
        r"mkfs.*",
        r"dd\s+if=.*of=/dev/.*",
        r"shutdown.*",
        r"reboot.*",
        r"kubectl\s+delete\s+(ns|namespace|deployment|cluster|all).*",
        r"aws\s+.*(terminate-instances|delete-db-instance|delete-bucket).*",
    ]

    # HTTP paths indicative of irreversible financial or resource mutation
    HTTP_COMMIT_PATHS = [
        r".*/checkout.*",
        r".*/charges.*",
        r".*/orders/confirm.*",
        r".*/transfers.*",
        r".*/payments/execute.*",
        r".*/v1/subscriptions/cancel.*",
        r".*/api/.*/delete.*",
    ]

    def __init__(self, custom_rules: Optional[List[Tuple[str, ActionTier]]] = None) -> None:
        self.custom_rules = custom_rules or []

    def classify(self, action: ActionPayload) -> ActionTier:
        """Determine safety tier for given action payload."""
        # 1. Check custom overrides first
        for pattern, tier in self.custom_rules:
            if re.search(pattern, action.target, re.IGNORECASE):
                return tier

        # 2. Check UI clicks
        if action.category == ActionCategory.UI_CLICK:
            return self._classify_ui_click(action)

        # 3. Check shell commands
        if action.category == ActionCategory.SHELL_COMMAND:
            return self._classify_shell_command(action)

        # 4. Check HTTP operations
        if action.category in (ActionCategory.HTTP_READ, ActionCategory.HTTP_MUTATE):
            return self._classify_http_request(action)

        # 5. Check File operations
        if action.category == ActionCategory.FILE_DELETE:
            return ActionTier.TIER_3_IRREVERSIBLE_COMMIT
        if action.category == ActionCategory.FILE_WRITE:
            return ActionTier.TIER_2_MUTATING
        if action.category == ActionCategory.FILE_READ:
            return ActionTier.TIER_0_READ_ONLY

        # 6. Check Database operations
        if action.category == ActionCategory.DB_MUTATE:
            sql = str(action.parameters.get("query", action.target)).strip().upper()
            if sql.startswith(("DROP", "TRUNCATE")):
                return ActionTier.TIER_3_IRREVERSIBLE_COMMIT
            return ActionTier.TIER_2_MUTATING
        if action.category == ActionCategory.DB_QUERY:
            return ActionTier.TIER_0_READ_ONLY

        # 7. Check UI keystrokes & navigation
        if action.category == ActionCategory.UI_KEYSTROKE:
            return ActionTier.TIER_1_REVERSIBLE
        if action.category in (ActionCategory.UI_SCROLL, ActionCategory.UI_NAVIGATION):
            return ActionTier.TIER_0_READ_ONLY

        # Default fallback
        return action.tier

    def _classify_ui_click(self, action: ActionPayload) -> ActionTier:
        target = action.target.lower()
        text = str(action.parameters.get("text", action.metadata.get("text", ""))).lower()
        aria_label = str(action.metadata.get("aria-label", "")).lower()

        # Check commit keywords in text or aria-label
        combined_text = f"{text} {aria_label}".strip()
        for kw in self.DOM_COMMIT_KEYWORDS:
            if kw in combined_text:
                return ActionTier.TIER_3_IRREVERSIBLE_COMMIT

        # Check selector regex
        for sel_pattern in self.DOM_COMMIT_SELECTORS:
            if re.search(sel_pattern, target, re.IGNORECASE):
                return ActionTier.TIER_3_IRREVERSIBLE_COMMIT

        # Non-commit clicks: e.g. add to cart is Tier 2 (mutating but not checkout commit)
        if "add-to-cart" in target or "add to cart" in combined_text:
            return ActionTier.TIER_2_MUTATING

        # Navigation / inspection clicks
        if any(w in target for w in ["nav", "tab", "filter", "search", "view", "details"]):
            return ActionTier.TIER_0_READ_ONLY

        # Neutral click default
        return ActionTier.TIER_1_REVERSIBLE

    def _classify_shell_command(self, action: ActionPayload) -> ActionTier:
        cmd = action.target.strip()
        for pat in self.SHELL_TIER3_PATTERNS:
            if re.search(pat, cmd, re.IGNORECASE):
                return ActionTier.TIER_3_IRREVERSIBLE_COMMIT

        # Read-only commands
        if re.match(r"^(ls|cat|head|tail|grep|find|pwd|echo|stat|ps|whoami)\b", cmd):
            return ActionTier.TIER_0_READ_ONLY

        # Reversible scratch commands
        if re.match(r"^(mkdir\s+/tmp/|touch\s+/tmp/|cd)\b", cmd):
            return ActionTier.TIER_1_REVERSIBLE

        return ActionTier.TIER_2_MUTATING

    def _classify_http_request(self, action: ActionPayload) -> ActionTier:
        method = str(action.parameters.get("method", "GET")).upper()
        url = action.target.lower()

        if method in ("GET", "HEAD", "OPTIONS"):
            return ActionTier.TIER_0_READ_ONLY

        if method == "DELETE":
            return ActionTier.TIER_3_IRREVERSIBLE_COMMIT

        for pat in self.HTTP_COMMIT_PATHS:
            if re.search(pat, url, re.IGNORECASE):
                return ActionTier.TIER_3_IRREVERSIBLE_COMMIT

        return ActionTier.TIER_2_MUTATING
