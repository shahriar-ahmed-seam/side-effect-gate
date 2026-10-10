"""SideGate: Dual-Layer State-Diff Verification and Multi-Tier Irreversible Action Gating Engine."""

__version__ = "0.2.0"
__author__ = "Shahriar Ahmed Seam"
__license__ = "Apache-2.0"

from sidegate.core.models import (
    ActionCategory,
    ActionPayload,
    ActionTier,
    ConstraintViolation,
    DualLayerAuditResult,
    GatingDecisionType,
    GoalPredicate,
    InterceptionDecision,
    InterceptionEvent,
    InterceptionLayer,
    Invariant,
    StateDelta,
    StateDomain,
    StateMutation,
    StateSnapshot,
)

__all__ = [
    "ActionCategory",
    "ActionPayload",
    "ActionTier",
    "ConstraintViolation",
    "DualLayerAuditResult",
    "GatingDecisionType",
    "GoalPredicate",
    "InterceptionDecision",
    "InterceptionEvent",
    "InterceptionLayer",
    "Invariant",
    "StateDelta",
    "StateDomain",
    "StateMutation",
    "StateSnapshot",
]
