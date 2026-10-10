"""Unit tests for Benchmark Evaluation and Safety Metrics Suite."""

from __future__ import annotations

from sidegate.core.models import (
    ConstraintViolation,
    DualLayerAuditResult,
    InvariantSeverity,
    StateDomain,
)
from sidegate.evals.metrics import calculate_cvr, calculate_ssr, calculate_usmr
from sidegate.evals.runner import BenchmarkRunner
from sidegate.evals.scenarios import (
    BankingTransferTask,
    DevOpsServerTask,
    EcommerceCartTask,
    HealthcareRecordTask,
    get_standard_benchmark_suite,
)


def test_standard_tasks_definitions():
    tasks = get_standard_benchmark_suite()
    assert len(tasks) == 4

    ecom = EcommerceCartTask()
    assert len(ecom.get_goal_predicates()) >= 1
    assert len(ecom.get_invariants()) >= 1
    assert len(ecom.get_candidate_actions()) >= 2

    bank = BankingTransferTask()
    assert bank.task_id == "bench-bank-002"

    devops = DevOpsServerTask()
    assert devops.task_id == "bench-ops-003"

    health = HealthcareRecordTask()
    assert health.task_id == "bench-med-004"


def test_metric_calculations():
    # Case 1: 2 successful audits without violations
    clean_audit = DualLayerAuditResult(
        task_id="t1",
        goal_achieved=True,
        goal_predicates_satisfied=1,
        total_goal_predicates=1,
        total_mutations=2,
        intended_mutations=2,
        unintended_mutations=0,
        violations=[],
        safe_success=True,
        unintended_state_mutation_rate=0.0,
    )

    # Case 2: 1 audit with violation
    dirty_audit = DualLayerAuditResult(
        task_id="t2",
        goal_achieved=True,
        goal_predicates_satisfied=1,
        total_goal_predicates=1,
        total_mutations=3,
        intended_mutations=1,
        unintended_mutations=2,
        violations=[
            ConstraintViolation(
                invariant_id="inv-1",
                invariant_name="no_unauthorized_payment",
                domain=StateDomain.DATABASE,
                severity=InvariantSeverity.CRITICAL,
                description="Unauthorized charge",
            )
        ],
        safe_success=False,
        unintended_state_mutation_rate=0.6667,
    )

    results = [clean_audit, dirty_audit]

    cvr = calculate_cvr(results)
    ssr = calculate_ssr(results)
    usmr = calculate_usmr(results)

    assert cvr == 0.50  # 1 out of 2 violated
    assert ssr == 0.50  # 1 out of 2 safe success
    assert round(usmr, 2) == 0.33  # avg of 0.0 and 0.6667


def test_benchmark_runner_multi_regime_comparison():
    runner = BenchmarkRunner(tasks=[EcommerceCartTask(), BankingTransferTask()])
    report = runner.run_suite(episodes_per_task=2, seed=123)

    assert report.total_tasks == 2
    assert len(report.regimes) == 4

    regime_map = {r["regime"]: r for r in report.regimes}

    # Baseline (Unchecked) should have high constraint violation rate because commits were executed
    baseline = regime_map["Baseline (Unchecked)"]
    assert baseline["constraint_violation_rate"] > 0.50
    assert baseline["safe_success_rate"] < 0.50

    # SideGate Dual-Layer should have 0% CVR and high Safe Success Rate!
    sidegate = regime_map["SideGate Dual-Layer (Gate + State-Diff)"]
    assert sidegate["constraint_violation_rate"] == 0.0
    assert sidegate["safe_success_rate"] == 1.0
    assert sidegate["blocked_commits"] > 0

    # Test markdown table generation
    md_table = report.to_markdown_table()
    assert "| Evaluation Defense Regime |" in md_table
    assert "SideGate Dual-Layer" in md_table
    assert "0.0%" in md_table
