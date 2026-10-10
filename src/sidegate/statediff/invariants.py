"""System invariant verification and constraint violation detection engine."""

from __future__ import annotations

import fnmatch
import re
from typing import List, Optional

from sidegate.core.models import (
    ConstraintViolation,
    Invariant,
    InvariantSeverity,
    MutationType,
    StateDelta,
    StateDomain,
    StateMutation,
    StateSnapshot,
)


class InvariantEvaluator:
    """Evaluates declarative invariant rules against observed state deltas and post snapshots."""

    def __init__(self, invariants: Optional[List[Invariant]] = None) -> None:
        self.invariants = invariants or []

    def add_invariant(self, invariant: Invariant) -> None:
        self.invariants.append(invariant)

    def evaluate(
        self,
        delta: StateDelta,
        post_snapshot: Optional[StateSnapshot] = None,
    ) -> List[ConstraintViolation]:
        """Evaluate all registered invariants against mutations in delta."""
        violations: List[ConstraintViolation] = []

        for inv in self.invariants:
            matched_mutations = [
                m for m in delta.mutations
                if m.domain == inv.domain and self._path_matches(m.path, inv.target_path)
            ]

            for mutation in matched_mutations:
                violation = self._check_rule(inv, mutation)
                if violation:
                    violations.append(violation)

        return violations

    def _path_matches(self, actual_path: str, target_pattern: str) -> bool:
        """Check path against target pattern using glob wildcards and prefix matching."""
        if actual_path == target_pattern:
            return True
        if fnmatch.fnmatch(actual_path, target_pattern):
            return True
        # Match parent array target against indexed child path (e.g. 'db.cart.items' vs 'db.cart.items[0]')
        if actual_path.startswith(f"{target_pattern}[") or actual_path.startswith(f"{target_pattern}."):
            return True
        # Also check without leading domain prefix (e.g. 'db.users' vs 'users')
        parts = actual_path.split(".", 1)
        if len(parts) > 1:
            if fnmatch.fnmatch(parts[1], target_pattern):
                return True
            if parts[1].startswith(f"{target_pattern}[") or parts[1].startswith(f"{target_pattern}."):
                return True
        return False

    def _check_rule(self, inv: Invariant, mutation: StateMutation) -> Optional[ConstraintViolation]:
        """Check specific invariant rule type against an observed mutation."""
        rule = inv.rule_type.lower()

        # Rule 1: Immutable (zero mutations allowed on target path)
        if rule == "immutable":
            return ConstraintViolation(
                invariant_id=inv.invariant_id,
                invariant_name=inv.name,
                domain=inv.domain,
                severity=inv.severity,
                description=(
                    f"Immutable path '{mutation.path}' was mutated ({mutation.mutation_type.value}): "
                    f"{mutation.old_value} -> {mutation.new_value}"
                ),
                detected_mutation=mutation,
            )

        # Rule 2: No Delete
        if rule == "no_delete" and mutation.mutation_type == MutationType.DELETED:
            return ConstraintViolation(
                invariant_id=inv.invariant_id,
                invariant_name=inv.name,
                domain=inv.domain,
                severity=inv.severity,
                description=f"Prohibited deletion detected on path '{mutation.path}'",
                detected_mutation=mutation,
            )

        # Rule 3: Min Value
        if rule == "min_value" and inv.constraint_param is not None:
            if isinstance(mutation.new_value, (int, float)):
                if mutation.new_value < float(inv.constraint_param):
                    return ConstraintViolation(
                        invariant_id=inv.invariant_id,
                        invariant_name=inv.name,
                        domain=inv.domain,
                        severity=inv.severity,
                        description=(
                            f"Value {mutation.new_value} on '{mutation.path}' fell below "
                            f"minimum threshold {inv.constraint_param}"
                        ),
                        detected_mutation=mutation,
                    )

        # Rule 4: Max Value
        if rule == "max_value" and inv.constraint_param is not None:
            if isinstance(mutation.new_value, (int, float)):
                if mutation.new_value > float(inv.constraint_param):
                    return ConstraintViolation(
                        invariant_id=inv.invariant_id,
                        invariant_name=inv.name,
                        domain=inv.domain,
                        severity=inv.severity,
                        description=(
                            f"Value {mutation.new_value} on '{mutation.path}' exceeded "
                            f"maximum threshold {inv.constraint_param}"
                        ),
                        detected_mutation=mutation,
                    )

        # Rule 5: Pattern Match / Regex Match
        if rule in ("pattern_match", "regex_match") and inv.constraint_param is not None:
            if isinstance(mutation.new_value, str):
                if not re.search(str(inv.constraint_param), mutation.new_value):
                    return ConstraintViolation(
                        invariant_id=inv.invariant_id,
                        invariant_name=inv.name,
                        domain=inv.domain,
                        severity=inv.severity,
                        description=(
                            f"Value '{mutation.new_value}' on '{mutation.path}' failed to match "
                            f"pattern '{inv.constraint_param}'"
                        ),
                        detected_mutation=mutation,
                    )

        # Rule 6: Allowed Values
        if rule == "allowed_values" and isinstance(inv.constraint_param, list):
            if mutation.new_value not in inv.constraint_param:
                return ConstraintViolation(
                    invariant_id=inv.invariant_id,
                    invariant_name=inv.name,
                    domain=inv.domain,
                    severity=inv.severity,
                    description=(
                        f"Value '{mutation.new_value}' on '{mutation.path}' not in allowed set "
                        f"{inv.constraint_param}"
                    ),
                    detected_mutation=mutation,
                )

        # Rule 7: No Decrease (monotonic non-decreasing)
        if rule == "no_decrease":
            if mutation.numeric_delta is not None and mutation.numeric_delta < 0:
                return ConstraintViolation(
                    invariant_id=inv.invariant_id,
                    invariant_name=inv.name,
                    domain=inv.domain,
                    severity=inv.severity,
                    description=(
                        f"Value on '{mutation.path}' decreased by {abs(mutation.numeric_delta)} "
                        f"({mutation.old_value} -> {mutation.new_value})"
                    ),
                    detected_mutation=mutation,
                )

        # Rule 8: No Increase (monotonic non-increasing)
        if rule == "no_increase":
            if mutation.numeric_delta is not None and mutation.numeric_delta > 0:
                return ConstraintViolation(
                    invariant_id=inv.invariant_id,
                    invariant_name=inv.name,
                    domain=inv.domain,
                    severity=inv.severity,
                    description=(
                        f"Value on '{mutation.path}' increased by {mutation.numeric_delta} "
                        f"({mutation.old_value} -> {mutation.new_value})"
                    ),
                    detected_mutation=mutation,
                )

        # Rule 9: Max Delta (absolute change threshold)
        if rule == "max_delta" and inv.constraint_param is not None:
            if mutation.numeric_delta is not None and abs(mutation.numeric_delta) > float(inv.constraint_param):
                return ConstraintViolation(
                    invariant_id=inv.invariant_id,
                    invariant_name=inv.name,
                    domain=inv.domain,
                    severity=inv.severity,
                    description=(
                        f"Absolute change of {abs(mutation.numeric_delta)} on '{mutation.path}' "
                        f"exceeded maximum delta threshold {inv.constraint_param}"
                    ),
                    detected_mutation=mutation,
                )

        return None


def create_balance_invariant(
    target_path: str = "db.account.balance",
    min_balance: float = 0.0,
    name: str = "preserve_account_balance",
) -> Invariant:
    """Helper factory for financial balance preservation constraints."""
    from sidegate.core.models import InvariantSeverity, StateDomain

    return Invariant(
        name=name,
        description=f"Account balance must not drop below {min_balance}",
        domain=StateDomain.DATABASE,
        target_path=target_path,
        rule_type="min_value",
        constraint_param=min_balance,
        severity=InvariantSeverity.CRITICAL,
    )


def create_immutable_invariant(
    domain: StateDomain,
    target_path: str,
    name: Optional[str] = None,
    severity: InvariantSeverity = InvariantSeverity.CRITICAL,
) -> Invariant:
    """Helper factory for immutability constraints."""
    inv_name = name or f"immutable_{target_path.replace('.', '_')}"
    return Invariant(
        name=inv_name,
        description=f"Target path {target_path} is strictly immutable",
        domain=domain,
        target_path=target_path,
        rule_type="immutable",
        severity=severity,
    )


def create_spend_limit_invariant(
    target_path: str = "db.account.balance",
    max_spend: float = 0.0,
    name: str = "monetary_spend_limit",
) -> Invariant:
    """Helper factory ensuring spent funds do not exceed a strict threshold."""
    from sidegate.core.models import InvariantSeverity, StateDomain

    return Invariant(
        name=name,
        description=f"Permitted expenditure cannot exceed {max_spend}",
        domain=StateDomain.DATABASE,
        target_path=target_path,
        rule_type="max_delta" if max_spend > 0 else "no_decrease",
        constraint_param=max_spend if max_spend > 0 else None,
        severity=InvariantSeverity.CRITICAL,
    )
