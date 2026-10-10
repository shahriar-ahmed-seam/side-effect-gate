"""Domain exception hierarchy for SideGate."""

from __future__ import annotations


class SideGateError(Exception):
    """Base exception for all SideGate domain errors."""


class IrreversibleActionBlockedError(SideGateError):
    """Raised when an irreversible Tier-3 action is intercepted and blocked by the runtime gate."""

    def __init__(self, action_id: str, reason: str = "", layer: str = "HARNESS") -> None:
        self.action_id = action_id
        self.reason = reason or "Irreversible Tier-3 commit action blocked"
        self.layer = layer
        super().__init__(
            f"Action '{action_id}' BLOCKED at {layer} layer: {self.reason}"
        )


class InvariantViolationError(SideGateError):
    """Raised when post-action state diff violates one or more system invariants."""

    def __init__(self, invariant_id: str, description: str, severity: str = "CRITICAL") -> None:
        self.invariant_id = invariant_id
        self.description = description
        self.severity = severity
        super().__init__(
            f"Invariant '{invariant_id}' [{severity}] VIOLATED: {description}"
        )


class StateSnapshotError(SideGateError):
    """Raised when environment state snapshotting fails."""


class PolicyEvaluationError(SideGateError):
    """Raised when an action gating policy expression cannot be parsed or evaluated."""
