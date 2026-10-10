"""Deterministic canonical state hashing utilities."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json_dumps(obj: Any) -> str:
    """Serialize object to deterministic, sorted canonical JSON string."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def compute_deterministic_hash(data: Any) -> str:
    """Compute deterministic SHA-256 hash digest of arbitrary JSON-compatible data structures.

    Recursively canonicalizes primitives, dictionaries, lists, and tuples.
    """
    if data is None:
        canonical_repr = "null"
    elif isinstance(data, (bool, int, float, str)):
        canonical_repr = canonical_json_dumps(data)
    elif isinstance(data, dict):
        normalized = {str(k): data[k] for k in sorted(data.keys())}
        canonical_repr = canonical_json_dumps(normalized)
    elif isinstance(data, (list, tuple, set)):
        normalized_list = list(data)
        canonical_repr = canonical_json_dumps(normalized_list)
    else:
        # Fallback to string representation
        canonical_repr = canonical_json_dumps(str(data))

    return hashlib.sha256(canonical_repr.encode("utf-8")).hexdigest()
