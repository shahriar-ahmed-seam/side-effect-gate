"""Deep recursive state diff engine computing atomic mutations and deltas."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

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

    FINANCIAL_KEYWORDS = (
        "balance",
        "credit",
        "amount",
        "price",
        "total",
        "spend",
        "spent",
        "charge",
        "payment",
        "fee",
        "cost",
    )

    IDENTITY_KEYS = ("id", "sku", "uuid", "key", "name", "task_id", "item_id")

    @classmethod
    def _is_financial_path(cls, path: str) -> bool:
        low = path.lower()
        return any(kw in low for kw in cls.FINANCIAL_KEYWORDS)

    @classmethod
    def _compute_numeric_delta(cls, old_val: Any, new_val: Any) -> Optional[float]:
        if isinstance(old_val, bool) or isinstance(new_val, bool):
            return None
        if isinstance(old_val, (int, float)) and isinstance(new_val, (int, float)):
            return round(float(new_val) - float(old_val), 4)
        return None

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
            val = post_dict[key]
            num_delta = (
                cls._compute_numeric_delta(0, val)
                if isinstance(val, (int, float)) and not isinstance(val, bool)
                else None
            )
            mutations.append(
                StateMutation(
                    domain=domain,
                    path=path,
                    mutation_type=MutationType.ADDED,
                    old_value=None,
                    new_value=val,
                    numeric_delta=num_delta,
                    is_financial=cls._is_financial_path(path),
                )
            )

        # Deleted keys
        for key in pre_keys - post_keys:
            path = f"{prefix}.{key}" if prefix else str(key)
            val = pre_dict[key]
            num_delta = (
                cls._compute_numeric_delta(val, 0)
                if isinstance(val, (int, float)) and not isinstance(val, bool)
                else None
            )
            mutations.append(
                StateMutation(
                    domain=domain,
                    path=path,
                    mutation_type=MutationType.DELETED,
                    old_value=val,
                    new_value=None,
                    numeric_delta=num_delta,
                    is_financial=cls._is_financial_path(path),
                )
            )

        # Common keys
        for key in pre_keys & post_keys:
            path = f"{prefix}.{key}" if prefix else str(key)
            val_pre = pre_dict[key]
            val_post = post_dict[key]

            if isinstance(val_pre, dict) and isinstance(val_post, dict):
                mutations.extend(cls._diff_dict(domain, val_pre, val_post, path))
            elif isinstance(val_pre, list) and isinstance(val_post, list):
                mutations.extend(cls._diff_list(domain, val_pre, val_post, path))
            elif val_pre != val_post:
                mutations.append(
                    StateMutation(
                        domain=domain,
                        path=path,
                        mutation_type=MutationType.MODIFIED,
                        old_value=val_pre,
                        new_value=val_post,
                        numeric_delta=cls._compute_numeric_delta(val_pre, val_post),
                        is_financial=cls._is_financial_path(path),
                    )
                )

        return mutations

    @classmethod
    def _diff_list(
        cls,
        domain: StateDomain,
        pre_list: List[Any],
        post_list: List[Any],
        prefix: str,
    ) -> List[StateMutation]:
        mutations: List[StateMutation] = []

        # Check if list of dicts with a common identity key
        id_key = cls._detect_identity_key(pre_list, post_list)

        if id_key:
            pre_map = {
                str(item[id_key]): item
                for item in pre_list
                if isinstance(item, dict) and id_key in item
            }
            post_map = {
                str(item[id_key]): item
                for item in post_list
                if isinstance(item, dict) and id_key in item
            }

            # Added items
            for item_id in post_map.keys() - pre_map.keys():
                item_val = post_map[item_id]
                item_path = f"{prefix}[{item_id}]"
                mutations.append(
                    StateMutation(
                        domain=domain,
                        path=item_path,
                        mutation_type=MutationType.ADDED,
                        old_value=None,
                        new_value=item_val,
                        is_financial=cls._is_financial_path(item_path),
                    )
                )

            # Deleted items
            for item_id in pre_map.keys() - post_map.keys():
                item_val = pre_map[item_id]
                item_path = f"{prefix}[{item_id}]"
                mutations.append(
                    StateMutation(
                        domain=domain,
                        path=item_path,
                        mutation_type=MutationType.DELETED,
                        old_value=item_val,
                        new_value=None,
                        is_financial=cls._is_financial_path(item_path),
                    )
                )

            # Common items: diff internal fields
            for item_id in pre_map.keys() & post_map.keys():
                item_pre = pre_map[item_id]
                item_post = post_map[item_id]
                item_path = f"{prefix}[{item_id}]"
                mutations.extend(cls._diff_dict(domain, item_pre, item_post, item_path))

            return mutations

        # Fallback: positional list diffing
        common_len = min(len(pre_list), len(post_list))
        for idx in range(common_len):
            idx_path = f"{prefix}[{idx}]"
            elem_pre = pre_list[idx]
            elem_post = post_list[idx]

            if isinstance(elem_pre, dict) and isinstance(elem_post, dict):
                mutations.extend(cls._diff_dict(domain, elem_pre, elem_post, idx_path))
            elif isinstance(elem_pre, list) and isinstance(elem_post, list):
                mutations.extend(cls._diff_list(domain, elem_pre, elem_post, idx_path))
            elif elem_pre != elem_post:
                mutations.append(
                    StateMutation(
                        domain=domain,
                        path=idx_path,
                        mutation_type=MutationType.MODIFIED,
                        old_value=elem_pre,
                        new_value=elem_post,
                        numeric_delta=cls._compute_numeric_delta(elem_pre, elem_post),
                        is_financial=cls._is_financial_path(idx_path),
                    )
                )

        # Added elements beyond common length
        for idx in range(common_len, len(post_list)):
            idx_path = f"{prefix}[{idx}]"
            val = post_list[idx]
            mutations.append(
                StateMutation(
                    domain=domain,
                    path=idx_path,
                    mutation_type=MutationType.ADDED,
                    old_value=None,
                    new_value=val,
                    numeric_delta=(
                        cls._compute_numeric_delta(0, val)
                        if isinstance(val, (int, float)) and not isinstance(val, bool)
                        else None
                    ),
                    is_financial=cls._is_financial_path(idx_path),
                )
            )

        # Deleted elements beyond common length
        for idx in range(common_len, len(pre_list)):
            idx_path = f"{prefix}[{idx}]"
            val = pre_list[idx]
            mutations.append(
                StateMutation(
                    domain=domain,
                    path=idx_path,
                    mutation_type=MutationType.DELETED,
                    old_value=val,
                    new_value=None,
                    numeric_delta=(
                        cls._compute_numeric_delta(val, 0)
                        if isinstance(val, (int, float)) and not isinstance(val, bool)
                        else None
                    ),
                    is_financial=cls._is_financial_path(idx_path),
                )
            )

        return mutations

    @classmethod
    def _detect_identity_key(cls, list_a: List[Any], list_b: List[Any]) -> Optional[str]:
        items = [x for x in list_a if isinstance(x, dict)] + [x for x in list_b if isinstance(x, dict)]
        if not items:
            return None
        for key in cls.IDENTITY_KEYS:
            if all(key in it for it in items):
                return key
        return None

    @classmethod
    def _diff_network_list(
        cls,
        pre_list: List[Dict[str, Any]],
        post_list: List[Dict[str, Any]],
    ) -> List[StateMutation]:
        return cls._diff_list(StateDomain.NETWORK, pre_list, post_list, "net.requests")
