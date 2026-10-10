"""Core domain models and schema definitions for SideGate."""

from __future__ import annotations

import time
import uuid
from enum import Enum, IntEnum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from sidegate.core.hash import compute_deterministic_hash


class ActionTier(IntEnum):
    """Action safety classification tiers.

    Tier 0: Pure read-only observers (inspection, screenshot, get DOM, read file).
    Tier 1: Idempotent or reversible mutations (typing into scratch buffers, focus, scrolling).
    Tier 2: Potentially destructive state mutations (modifying cart, document edits, non-commit updates).
    Tier 3: Irreversible commits (checkout/payment clicks, fund transfers, deleting production records, external webhooks).
    """

    TIER_0_READ_ONLY = 0
    TIER_1_REVERSIBLE = 1
    TIER_2_MUTATING = 2
    TIER_3_IRREVERSIBLE_COMMIT = 3


class ActionCategory(str, Enum):
    """Categorical classification of agent action payloads."""

    UI_CLICK = "ui_click"
    UI_KEYSTROKE = "ui_keystroke"
    UI_SCROLL = "ui_scroll"
    UI_NAVIGATION = "ui_navigation"
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_DELETE = "file_delete"
    DB_QUERY = "db_query"
    DB_MUTATE = "db_mutate"
    HTTP_READ = "http_read"
    HTTP_MUTATE = "http_mutate"
    SHELL_COMMAND = "shell_command"
    TOOL_INVOCATION = "tool_invocation"


class ActionPayload(BaseModel):
    """Standardized representation of a computer-use agent action."""

    action_id: str = Field(default_factory=lambda: f"act-{uuid.uuid4().hex[:10]}")
    tier: ActionTier = Field(default=ActionTier.TIER_0_READ_ONLY)
    category: ActionCategory = Field(default=ActionCategory.UI_CLICK)
    target: str = Field(description="Target DOM selector, endpoint URL, file path, or command string")
    parameters: Dict[str, Any] = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def is_irreversible(self) -> bool:
        """Check whether this action is classified as an irreversible commit."""
        return self.tier == ActionTier.TIER_3_IRREVERSIBLE_COMMIT


class StateDomain(str, Enum):
    """Subsystem domains for environment state snapshotting and mutation tracking."""

    DOM = "dom"
    DATABASE = "database"
    FILESYSTEM = "filesystem"
    NETWORK = "network"
    APPLICATION_CONTEXT = "application_context"


class MutationType(str, Enum):
    """Type of state change observed between pre and post snapshots."""

    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"


class StateMutation(BaseModel):
    """Atomic delta observed on a specific state path."""

    domain: StateDomain
    path: str
    mutation_type: MutationType
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    numeric_delta: Optional[float] = None
    is_financial: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)


class StateSnapshot(BaseModel):
    """Point-in-time canonical snapshot of all monitored system state domains."""

    snapshot_id: str = Field(default_factory=lambda: f"snap-{uuid.uuid4().hex[:10]}")
    timestamp: float = Field(default_factory=time.time)
    dom_state: Dict[str, Any] = Field(default_factory=dict)
    db_state: Dict[str, Any] = Field(default_factory=dict)
    fs_state: Dict[str, Any] = Field(default_factory=dict)
    network_state: List[Dict[str, Any]] = Field(default_factory=list)
    context_state: Dict[str, Any] = Field(default_factory=dict)
    state_hash: Optional[str] = None

    def model_post_init(self, __context: Any) -> None:
        if not self.state_hash:
            self.state_hash = self.compute_hash()

    def compute_hash(self) -> str:
        """Calculate deterministic SHA-256 digest of entire snapshot payload."""
        combined = {
            "dom": self.dom_state,
            "db": self.db_state,
            "fs": self.fs_state,
            "net": self.network_state,
            "ctx": self.context_state,
        }
        return compute_deterministic_hash(combined)


class StateDelta(BaseModel):
    """Calculated difference between pre-execution and post-execution state snapshots."""

    delta_id: str = Field(default_factory=lambda: f"delta-{uuid.uuid4().hex[:10]}")
    pre_snapshot_id: str
    post_snapshot_id: str
    mutations: List[StateMutation] = Field(default_factory=list)
    total_mutations: int = 0
    financial_impact: float = 0.0
    domain_breakdown: Dict[str, int] = Field(default_factory=dict)
    checksum: str = ""

    def model_post_init(self, __context: Any) -> None:
        self.total_mutations = len(self.mutations)
        breakdown: Dict[str, int] = {}
        fin_impact = 0.0
        for m in self.mutations:
            breakdown[m.domain.value] = breakdown.get(m.domain.value, 0) + 1
            if m.numeric_delta is not None and m.is_financial:
                fin_impact += m.numeric_delta
        self.domain_breakdown = breakdown
        self.financial_impact = round(fin_impact, 4)
        if not self.checksum:
            mutation_dicts = [m.model_dump() for m in self.mutations]
            self.checksum = compute_deterministic_hash(mutation_dicts)


class GoalPredicate(BaseModel):
    """Predicate defining successful task completion conditions."""

    predicate_id: str = Field(default_factory=lambda: f"goal-{uuid.uuid4().hex[:8]}")
    description: str
    domain: StateDomain = Field(default=StateDomain.APPLICATION_CONTEXT)
    target_path: str
    expected_value: Any
    condition: str = Field(
        default="equals",
        description="Condition operator: equals, contains, exists, greater_than, less_than",
    )


class InvariantSeverity(str, Enum):
    """Severity classification of an invariant violation."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Invariant(BaseModel):
    """System invariant constraint that must NOT be violated by agent operations."""

    invariant_id: str = Field(default_factory=lambda: f"inv-{uuid.uuid4().hex[:8]}")
    name: str
    description: str
    domain: StateDomain
    target_path: str
    rule_type: str = Field(
        default="immutable",
        description="Rule type: immutable, no_delete, max_value, min_value, pattern_match, no_unintended_mutation",
    )
    constraint_param: Optional[Any] = None
    severity: InvariantSeverity = Field(default=InvariantSeverity.CRITICAL)


class ConstraintViolation(BaseModel):
    """Recorded violation of an invariant constraint during agent execution."""

    violation_id: str = Field(default_factory=lambda: f"viol-{uuid.uuid4().hex[:8]}")
    invariant_id: str
    invariant_name: str
    domain: StateDomain
    severity: InvariantSeverity
    description: str
    detected_mutation: Optional[StateMutation] = None
    timestamp: float = Field(default_factory=time.time)


class GatingDecisionType(str, Enum):
    """Gating verdict for an intercepted agent action."""

    PERMITTED = "PERMITTED"
    MONITORED = "MONITORED"
    BLOCKED = "BLOCKED"
    PENDING_CONFIRMATION = "PENDING_CONFIRMATION"


class InterceptionLayer(str, Enum):
    """Defense interception layer where action was evaluated."""

    HARNESS = "HARNESS"
    DOM = "DOM"
    NETWORK = "NETWORK"


class InterceptionDecision(BaseModel):
    """Evaluation verdict produced by the Irreversible Action Gate."""

    decision_id: str = Field(default_factory=lambda: f"dec-{uuid.uuid4().hex[:10]}")
    action_id: str
    tier: ActionTier
    layer: InterceptionLayer
    decision: GatingDecisionType
    reason: str
    rule_matched: Optional[str] = None
    confirmation_token: Optional[str] = None
    timestamp: float = Field(default_factory=time.time)


class InterceptionEvent(BaseModel):
    """Telemetry log record capturing the complete context of an intercepted action."""

    event_id: str = Field(default_factory=lambda: f"evt-{uuid.uuid4().hex[:10]}")
    timestamp: float = Field(default_factory=time.time)
    action: ActionPayload
    decision: InterceptionDecision
    active_invariants: List[str] = Field(default_factory=list)
    context: Dict[str, Any] = Field(default_factory=dict)


class DualLayerAuditResult(BaseModel):
    """Consolidated post-task audit combining runtime gating logs and state-diff verification."""

    audit_id: str = Field(default_factory=lambda: f"audit-{uuid.uuid4().hex[:10]}")
    task_id: str
    goal_achieved: bool
    goal_predicates_satisfied: int
    total_goal_predicates: int
    total_mutations: int
    intended_mutations: int
    unintended_mutations: int
    violations: List[ConstraintViolation] = Field(default_factory=list)
    constraint_violation_rate: float = 0.0
    unintended_state_mutation_rate: float = 0.0
    safe_success: bool = False
    financial_leakage: float = 0.0
    interception_events: List[InterceptionEvent] = Field(default_factory=list)
    timestamp: float = Field(default_factory=time.time)
