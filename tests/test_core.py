"""Unit tests for SideGate core domain models, hashing, and schemas."""

from __future__ import annotations

from sidegate.core.exceptions import (
    InvariantViolationError,
    IrreversibleActionBlockedError,
    SideGateError,
)
from sidegate.core.hash import compute_deterministic_hash
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
    InvariantSeverity,
    MutationType,
    StateDelta,
    StateDomain,
    StateMutation,
    StateSnapshot,
)


def test_action_tier_ordering_and_classification():
    assert ActionTier.TIER_0_READ_ONLY < ActionTier.TIER_1_REVERSIBLE
    assert ActionTier.TIER_1_REVERSIBLE < ActionTier.TIER_2_MUTATING
    assert ActionTier.TIER_2_MUTATING < ActionTier.TIER_3_IRREVERSIBLE_COMMIT

    action_read = ActionPayload(
        tier=ActionTier.TIER_0_READ_ONLY,
        category=ActionCategory.FILE_READ,
        target="/tmp/test.txt",
    )
    assert not action_read.is_irreversible()

    action_checkout = ActionPayload(
        tier=ActionTier.TIER_3_IRREVERSIBLE_COMMIT,
        category=ActionCategory.UI_CLICK,
        target="button#checkout-submit",
    )
    assert action_checkout.is_irreversible()


def test_deterministic_hashing():
    d1 = {"b": 2, "a": 1, "c": [3, 4]}
    d2 = {"a": 1, "c": [3, 4], "b": 2}

    h1 = compute_deterministic_hash(d1)
    h2 = compute_deterministic_hash(d2)

    assert h1 == h2
    assert len(h1) == 64  # SHA-256 length

    d3 = {"a": 1, "b": 2, "c": [3, 5]}
    h3 = compute_deterministic_hash(d3)
    assert h1 != h3


def test_state_snapshot_hashing_and_lifecycle():
    snap = StateSnapshot(
        dom_state={"body": {"children": ["div#cart"]}},
        db_state={"orders": [{"id": 1, "status": "pending"}]},
        fs_state={"files": ["/app/config.json"]},
        network_state=[{"url": "https://api.shop.com/cart", "method": "GET"}],
        context_state={"user_id": "usr-123"},
    )
    assert snap.state_hash is not None
    assert len(snap.state_hash) == 64

    # Verify identical data creates identical hash
    snap_copy = StateSnapshot(
        dom_state=snap.dom_state,
        db_state=snap.db_state,
        fs_state=snap.fs_state,
        network_state=snap.network_state,
        context_state=snap.context_state,
    )
    assert snap.state_hash == snap_copy.state_hash


def test_state_delta_and_mutations():
    mut = StateMutation(
        domain=StateDomain.DATABASE,
        path="accounts.usr-1.balance",
        mutation_type=MutationType.MODIFIED,
        old_value=1000.0,
        new_value=450.0,
    )
    delta = StateDelta(
        pre_snapshot_id="snap-pre",
        post_snapshot_id="snap-post",
        mutations=[mut],
    )
    assert delta.total_mutations == 1
    assert len(delta.checksum) == 64


def test_invariants_and_violations():
    inv = Invariant(
        name="account_balance_immutable",
        description="Account balance must not be modified by observer task",
        domain=StateDomain.DATABASE,
        target_path="accounts.*.balance",
        rule_type="immutable",
        severity=InvariantSeverity.CRITICAL,
    )
    assert inv.severity == InvariantSeverity.CRITICAL

    viol = ConstraintViolation(
        invariant_id=inv.invariant_id,
        invariant_name=inv.name,
        domain=inv.domain,
        severity=inv.severity,
        description="Unauthorized balance alteration detected",
    )
    assert viol.invariant_name == "account_balance_immutable"

    goal = GoalPredicate(
        description="Verify item was added to cart",
        domain=StateDomain.APPLICATION_CONTEXT,
        target_path="cart.items_count",
        expected_value=1,
        condition="equals",
    )
    assert goal.condition == "equals"
    assert goal.expected_value == 1


def test_interception_decision_and_audit():
    action = ActionPayload(
        tier=ActionTier.TIER_3_IRREVERSIBLE_COMMIT,
        category=ActionCategory.UI_CLICK,
        target="button#complete-wire-transfer",
    )
    decision = InterceptionDecision(
        action_id=action.action_id,
        tier=action.tier,
        layer=InterceptionLayer.DOM,
        decision=GatingDecisionType.BLOCKED,
        reason="Blocked irreversible Tier-3 transfer action click",
        rule_matched="rule-dom-commit-button",
    )
    event = InterceptionEvent(
        action=action,
        decision=decision,
        active_invariants=["inv-balance-min"],
    )
    assert event.decision.decision == GatingDecisionType.BLOCKED

    audit = DualLayerAuditResult(
        task_id="task-eval-001",
        goal_achieved=True,
        goal_predicates_satisfied=1,
        total_goal_predicates=1,
        total_mutations=2,
        intended_mutations=1,
        unintended_mutations=1,
        constraint_violation_rate=0.0,
        unintended_state_mutation_rate=0.5,
        safe_success=True,
        interception_events=[event],
    )
    assert audit.unintended_state_mutation_rate == 0.5


def test_custom_exceptions():
    err = IrreversibleActionBlockedError("act-1", "Checkout click blocked", "DOM")
    assert isinstance(err, SideGateError)
    assert "DOM" in str(err)

    inv_err = InvariantViolationError("inv-1", "Balance changed", "CRITICAL")
    assert "CRITICAL" in str(inv_err)
