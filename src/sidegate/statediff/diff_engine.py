"""Deep recursive state diff engine computing atomic mutations and deltas."""

from __future__ import annotations

from typing import Any, Dict, List

from sidegate.core.models import (
    MutationType,
    StateDelta,
    StateDomain,
    StateMutation,
    StateSnapshot,
)


class StateDiffEngine:
    """Computes exact structural difference between pre and post state snapshots."""

    @classmethod
    def compute_diff(
        cls,
        pre_snapshot: StateSnapshot,
        post_snapshot: StateSnapshot,
    ) -> StateDelta:
        """Compute atomic mutations between pre and post snapshots across all domains."""
        mutations: List[StateMutation] = []

        # 1. Diff DOM domain
        mutations.extend(
            cls._diff_dict(
                domain=StateDomain.DOM,
                pre_dict=pre_snapshot.dom_state,
                post_dict=post_snapshot.dom_state,
                prefix="dom",
            )
        )

        # 2. Diff Database domain
        mutations.extend(
            cls._diff_dict(
                domain=StateDomain.DATABASE,
                pre_dict=pre_snapshot.db_state,
                post_dict=post_snapshot.db_state,
                prefix="db",
            )
        )

        # 3. Diff Filesystem domain
        mutations.extend(
            cls._diff_dict(
                domain=StateDomain.FILESYSTEM,
                pre_dict=pre_snapshot.fs_state,
                post_dict=post_snapshot.fs_state,
                prefix="fs",
            )
        )

        # 4. Diff Network domain (list of entries)
        mutations.extend(
            cls._diff_network_list(
                pre_list=pre_snapshot.network_state,
                post_list=post_snapshot.network_state,
            )
        )

        # 5. Diff Context domain
        mutations.extend(
            cls._diff_dict(
                domain=StateDomain.APPLICATION_CONTEXT,
                pre_dict=pre_snapshot.context_state,
                post_dict=post_snapshot.context_state,
                prefix="ctx",
            )
        )

        return StateDelta(
            pre_snapshot_id=pre_snapshot.snapshot_id,
            post_snapshot_id=post_snapshot.snapshot_id,
            mutations=mutations,
        )

    @classmethod
    def _diff_dict(
        cls,
        domain: StateDomain,
        pre_dict: Dict[str, Any],
        post_dict: Dict[str, Any],
        prefix: str,
    ) -> List[StateMutation]:
        mutations: List[StateMutation] = []
        pre_keys = set(pre_dict.keys())
        post_keys = set(post_dict.keys())

        # Added keys
        for key in post_keys - pre_keys:
            path = f"{prefix}.{key}" if prefix else str(key)
            mutations.append(
                StateMutation(
                    domain=domain,
                    path=path,
                    mutation_type=MutationType.ADDED,
                    old_value=None,
                    new_value=post_dict[key],
                )
            )

        # Deleted keys
        for key in pre_keys - post_keys:
            path = f"{prefix}.{key}" if prefix else str(key)
            mutations.append(
                StateMutation(
                    domain=domain,
                    path=path,
                    mutation_type=MutationType.DELETED,
                    old_value=pre_dict[key],
                    new_value=None,
                )
            )

        # Common keys
        for key in pre_keys & post_keys:
            path = f"{prefix}.{key}" if prefix else str(key)
            val_pre = pre_dict[key]
            val_post = post_dict[key]

            if isinstance(val_pre, dict) and isinstance(val_post, dict):
                mutations.extend(cls._diff_dict(domain, val_pre, val_post, path))
            elif val_pre != val_post:
                mutations.append(
                    StateMutation(
                        domain=domain,
                        path=path,
                        mutation_type=MutationType.MODIFIED,
                        old_value=val_pre,
                        new_value=val_post,
                    )
                )

        return mutations

    @classmethod
    def _diff_network_list(
        cls,
        pre_list: List[Dict[str, Any]],
        post_list: List[Dict[str, Any]],
    ) -> List[StateMutation]:
        mutations: List[StateMutation] = []
        # Added requests in post_list beyond pre_list length
        if len(post_list) > len(pre_list):
            for idx in range(len(pre_list), len(post_list)):
                mutations.append(
                    StateMutation(
                        domain=StateDomain.NETWORK,
                        path=f"net.requests[{idx}]",
                        mutation_type=MutationType.ADDED,
                        old_value=None,
                        new_value=post_list[idx],
                    )
                )
        return mutations
