"""State snapshot providers across DOM, database, filesystem, and network domains."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from sidegate.core.hash import compute_deterministic_hash
from sidegate.core.models import StateDomain, StateSnapshot


class BaseSnapshotProvider(ABC):
    """Abstract interface for domain-specific state snapshot providers."""

    @property
    @abstractmethod
    def domain(self) -> StateDomain:
        """Domain type identifier."""

    @abstractmethod
    def capture(self) -> Any:
        """Capture point-in-time domain state."""


class DOMSnapshotProvider(BaseSnapshotProvider):
    """Captures structured DOM hierarchy, interactive inputs, and document tree."""

    @property
    def domain(self) -> StateDomain:
        return StateDomain.DOM

    def __init__(self, extractor_fn: Optional[Any] = None) -> None:
        self.extractor_fn = extractor_fn

    def capture(self) -> Dict[str, Any]:
        if self.extractor_fn:
            return self.extractor_fn()
        return {}


class DatabaseSnapshotProvider(BaseSnapshotProvider):
    """Captures key-value store state, tables, or database entity state."""

    @property
    def domain(self) -> StateDomain:
        return StateDomain.DATABASE

    def __init__(self, source_dict: Optional[Dict[str, Any]] = None) -> None:
        self._source_dict = source_dict if source_dict is not None else {}

    def set_source(self, data: Dict[str, Any]) -> None:
        self._source_dict = data

    def capture(self) -> Dict[str, Any]:
        # Return deep copy of dictionary state
        import copy
        return copy.deepcopy(self._source_dict)


class FilesystemSnapshotProvider(BaseSnapshotProvider):
    """Captures file inventory, sizes, and deterministic hashes in a monitored directory."""

    @property
    def domain(self) -> StateDomain:
        return StateDomain.FILESYSTEM

    def __init__(self, root_dir: Optional[str] = None) -> None:
        self.root_dir = root_dir

    def capture(self) -> Dict[str, Any]:
        if not self.root_dir or not os.path.exists(self.root_dir):
            return {}

        file_tree: Dict[str, Any] = {}
        for root, _, files in os.walk(self.root_dir):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, self.root_dir)
                try:
                    size = os.path.getsize(full_path)
                    with open(full_path, "rb") as f:
                        content_hash = compute_deterministic_hash(f.read().decode("utf-8", errors="ignore"))
                    file_tree[rel_path] = {"size": size, "hash": content_hash}
                except (IOError, OSError):
                    file_tree[rel_path] = {"size": -1, "hash": "error"}
        return file_tree


class NetworkSnapshotProvider(BaseSnapshotProvider):
    """Captures outgoing network transaction logs and egress records."""

    @property
    def domain(self) -> StateDomain:
        return StateDomain.NETWORK

    def __init__(self) -> None:
        self._log: List[Dict[str, Any]] = []

    def record_request(self, entry: Dict[str, Any]) -> None:
        self._log.append(entry)

    def capture(self) -> List[Dict[str, Any]]:
        import copy
        return copy.deepcopy(self._log)


class CompositeSnapshotProvider:
    """Orchestrates comprehensive multi-domain state snapshotting."""

    def __init__(
        self,
        dom_provider: Optional[DOMSnapshotProvider] = None,
        db_provider: Optional[DatabaseSnapshotProvider] = None,
        fs_provider: Optional[FilesystemSnapshotProvider] = None,
        net_provider: Optional[NetworkSnapshotProvider] = None,
    ) -> None:
        self.dom_provider = dom_provider or DOMSnapshotProvider()
        self.db_provider = db_provider or DatabaseSnapshotProvider()
        self.fs_provider = fs_provider or FilesystemSnapshotProvider()
        self.net_provider = net_provider or NetworkSnapshotProvider()

    def snapshot(self, context_state: Optional[Dict[str, Any]] = None) -> StateSnapshot:
        """Capture holistic system snapshot across all active domains."""
        return StateSnapshot(
            dom_state=self.dom_provider.capture(),
            db_state=self.db_provider.capture(),
            fs_state=self.fs_provider.capture(),
            network_state=self.net_provider.capture(),
            context_state=context_state or {},
        )
