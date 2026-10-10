"""Automated benchmark runner comparing agent safety across multi-layer defense regimes."""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from sidegate.core.exceptions import IrreversibleActionBlockedError
from sidegate.core.models import (
    DualLayerAuditResult,
    GatingDecisionType,
    InterceptionDecision,
    InterceptionEvent,
    InterceptionLayer,
)
from sidegate.evals.metrics import aggregate_regime_summary
from sidegate.evals.scenarios import BaseBenchmarkTask, get_standard_benchmark_suite
from sidegate.gating.gate import GatingPolicy, RuntimeActionGate
from sidegate.statediff.invariants import InvariantEvaluator
from sidegate.statediff.verifier import DualLayerVerificationEngine


class BenchmarkSuiteReport(BaseModel):
    """Consolidated benchmark report comparing regimes across safety and performance metrics."""

    total_tasks: int
    episodes_per_regime: int
    regimes: List[Dict[str, Any]] = Field(default_factory=list)
    task_summaries: List[Dict[str, Any]] = Field(default_factory=list)

    def to_markdown_table(self) -> str:
        """Render publication-grade comparative evaluation markdown table."""
        lines = [
            "| Evaluation Defense Regime | Task Success Rate | Constraint Violation Rate (CVR) | Safe Success Rate (SSR) | Unintended Mutation Rate (USMR) | Blocked Commits |",
            "|---|---|---|---|---|---|",
        ]
        for r in self.regimes:
            lines.append(
                f"| **{r['regime']}** | "
                f"{r['task_success_rate'] * 100:.1f}% | "
                f"{r['constraint_violation_rate'] * 100:.1f}% | "
                f"{r['safe_success_rate'] * 100:.1f}% | "
                f"{r['unintended_mutation_rate'] * 100:.1f}% | "
                f"{r['blocked_commits']} |"
            )
        return "\n".join(lines)


class BenchmarkRunner:
    """Orchestrates comprehensive multi-regime evaluation across standardized task benchmarks."""

    def __init__(self, tasks: Optional[List[BaseBenchmarkTask]] = None) -> None:
        self.tasks = tasks or get_standard_benchmark_suite()

    def run_suite(self, episodes_per_task: int = 5, seed: int = 42) -> BenchmarkSuiteReport:
        """Execute full evaluation matrix across 4 defense regimes."""
        random.seed(seed)

        regime_results: Dict[str, List[DualLayerAuditResult]] = {
            "Baseline (Unchecked)": [],
            "System Prompt Only ('Do NOT check out')": [],
            "Outcome-Only Verification": [],
            "SideGate Dual-Layer (Gate + State-Diff)": [],
        }

        task_summaries = []

        for task in self.tasks:
            # 1. Run Baseline Unchecked
            base_audits = self._run_regime_for_task(
                task, episodes_per_task, regime="BASELINE"
            )
            regime_results["Baseline (Unchecked)"].extend(base_audits)

            # 2. Run System Prompt Only
            prompt_audits = self._run_regime_for_task(
                task, episodes_per_task, regime="SYSTEM_PROMPT"
            )
            regime_results["System Prompt Only ('Do NOT check out')"].extend(prompt_audits)

            # 3. Run Outcome-Only Verification
            outcome_audits = self._run_regime_for_task(
                task, episodes_per_task, regime="OUTCOME_ONLY"
            )
            regime_results["Outcome-Only Verification"].extend(outcome_audits)

            # 4. Run Dual-Layer SideGate
            sidegate_audits = self._run_regime_for_task(
                task, episodes_per_task, regime="SIDEGATE"
            )
            regime_results["SideGate Dual-Layer (Gate + State-Diff)"].extend(sidegate_audits)

            task_summaries.append({
                "task_id": task.task_id,
                "name": task.name,
                "goal_predicates": len(task.get_goal_predicates()),
                "invariants": len(task.get_invariants()),
            })

        summaries = [
            aggregate_regime_summary(regime_name, results)
            for regime_name, results in regime_results.items()
        ]

        return BenchmarkSuiteReport(
            total_tasks=len(self.tasks),
            episodes_per_regime=len(self.tasks) * episodes_per_task,
            regimes=summaries,
            task_summaries=task_summaries,
        )

    def _run_regime_for_task(
        self,
        task: BaseBenchmarkTask,
        episodes: int,
        regime: str,
    ) -> List[DualLayerAuditResult]:
        audits: List[DualLayerAuditResult] = []

        for ep_idx in range(episodes):
            pre_state = task.get_initial_state()
            current_state = task.get_initial_state()
            actions = task.get_candidate_actions()
            interception_events: List[InterceptionEvent] = []

            gate = RuntimeActionGate(policy=GatingPolicy(mode="ENFORCE"))
            verifier = DualLayerVerificationEngine(
                invariant_evaluator=InvariantEvaluator(task.get_invariants())
            )

            for action in actions:
                if regime == "BASELINE" or regime == "OUTCOME_ONLY":
                    # Blind execution without interception
                    current_state = task.apply_action(current_state, action)

                elif regime == "SYSTEM_PROMPT":
                    # Prompting compliance simulation: model compliance rate ~ 40% under fatigue
                    tier = gate.classifier.classify(action)
                    if tier.value >= 3 and random.random() < 0.40:
                        # Model complied with system prompt instruction
                        event = InterceptionEvent(
                            action=action,
                            decision=InterceptionDecision(
                                action_id=action.action_id,
                                tier=tier,
                                layer=InterceptionLayer.HARNESS,
                                decision=GatingDecisionType.BLOCKED,
                                reason="Complied with system prompt heuristic",
                            ),
                        )
                        interception_events.append(event)
                        continue

                    # Failed prompt enforcement: action executed anyway
                    current_state = task.apply_action(current_state, action)

                elif regime == "SIDEGATE":
                    # Multi-Tier Irreversible Action Gate enforcement
                    try:
                        dec = gate.evaluate_action(action)
                        if dec.decision == GatingDecisionType.BLOCKED:
                            # Blocked before execution
                            interception_events.append(
                                InterceptionEvent(action=action, decision=dec)
                            )
                            continue
                        current_state = task.apply_action(current_state, action)
                    except IrreversibleActionBlockedError:
                        # Hard interception caught before state mutation
                        tier = gate.classifier.classify(action)
                        dec = InterceptionDecision(
                            action_id=action.action_id,
                            tier=tier,
                            layer=InterceptionLayer.HARNESS,
                            decision=GatingDecisionType.BLOCKED,
                            reason=f"Blocked irreversible commit: {action.target}",
                        )
                        interception_events.append(
                            InterceptionEvent(action=action, decision=dec)
                        )
                        continue

            audit = verifier.audit(
                task_id=f"{task.task_id}-ep{ep_idx}",
                pre_snapshot=pre_state,
                post_snapshot=current_state,
                goal_predicates=task.get_goal_predicates(),
                interception_events=interception_events,
            )
            audits.append(audit)

        return audits
