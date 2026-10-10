"""System invariant verification and constraint violation detection engine."""

from __future__ import annotations

import fnmatch
import re
from typing import List, Optional

from sidegate.core.models import (
    ConstraintViolation,
    Invariant,
    MutationType,
    StateDelta,
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
        # Also check without leading domain prefix (e.g. 'db.users' vs 'users')
        parts = actual_path.split(".", 1)
        if len(parts) > 1 and fnmatch.fnmatch(parts[1], target_pattern):
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

        # Rule 5: Pattern Match
        if rule == "pattern_match" and inv.constraint_param is not None:
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

        return None
