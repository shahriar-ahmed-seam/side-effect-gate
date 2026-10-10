# SideGate Formal Specification: RFC-SG-001

## Abstract

This document defines the formal data models, serialization protocols, and validation semantics for the SideGate dual-layer runtime verification framework.

---

## 1. Action Model & Safety Tiers

### 1.1 ActionTier Enumeration

```text
enum ActionTier:
    TIER_0_READ_ONLY = 0
    TIER_1_REVERSIBLE = 1
    TIER_2_MUTATING = 2
    TIER_3_IRREVERSIBLE_COMMIT = 3
```

### 1.2 ActionPayload Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "ActionPayload",
  "type": "object",
  "properties": {
    "action_id": { "type": "string" },
    "tier": { "type": "integer", "minimum": 0, "maximum": 3 },
    "category": {
      "type": "string",
      "enum": [
        "ui_click", "ui_keystroke", "ui_scroll", "ui_navigation",
        "file_read", "file_write", "file_delete",
        "db_query", "db_mutate", "http_read", "http_mutate",
        "shell_command", "tool_invocation"
      ]
    },
    "target": { "type": "string" },
    "parameters": { "type": "object" },
    "timestamp": { "type": "number" },
    "metadata": { "type": "object" }
  },
  "required": ["action_id", "tier", "category", "target"]
}
```

---

## 2. State Snapshot & Structural Delta

### 2.1 StateSnapshot Schema

Point-in-time canonical representation of monitored environments.

```json
{
  "title": "StateSnapshot",
  "type": "object",
  "properties": {
    "snapshot_id": { "type": "string" },
    "timestamp": { "type": "number" },
    "dom_state": { "type": "object" },
    "db_state": { "type": "object" },
    "fs_state": { "type": "object" },
    "network_state": { "type": "array", "items": { "type": "object" } },
    "context_state": { "type": "object" },
    "state_hash": { "type": "string", "pattern": "^[a-f0-9]{64}$" }
  },
  "required": ["snapshot_id", "timestamp", "state_hash"]
}
```

### 2.2 StateDelta & StateMutation Schema

```json
{
  "title": "StateMutation",
  "type": "object",
  "properties": {
    "domain": { "type": "string", "enum": ["dom", "database", "filesystem", "network", "application_context"] },
    "path": { "type": "string" },
    "mutation_type": { "type": "string", "enum": ["added", "modified", "deleted"] },
    "old_value": {},
    "new_value": {},
    "metadata": { "type": "object" }
  },
  "required": ["domain", "path", "mutation_type"]
}
```

---

## 3. Invariants & Goal Predicates

### 3.1 Invariant Rules

System invariants define constraints that must NOT be violated.

- `immutable`: Target path must experience zero mutations ($\Delta S[\text{path}] = \emptyset$).
- `no_delete`: Target path must not experience deletion mutations.
- `min_value`: Observed numerical value on path must satisfy $v \ge \text{threshold}$.
- `max_value`: Observed numerical value on path must satisfy $v \le \text{threshold}$.
- `pattern_match`: String value on path must match regular expression pattern.
- `allowed_values`: Value on path must belong to finite set $V_{\text{allowed}}$.

### 3.2 Goal Predicate Evaluation

Goal predicates evaluate task completion criteria:

$$\text{Satisfied}(P, S_{\text{post}}) \iff \text{Condition}(S_{\text{post}}[\text{path}], \text{expected\_value}) = \text{True}$$

---

## 4. Decision Protocol & Interception

```text
enum GatingDecisionType:
    PERMITTED = "PERMITTED"
    MONITORED = "MONITORED"
    BLOCKED = "BLOCKED"
    PENDING_CONFIRMATION = "PENDING_CONFIRMATION"

enum InterceptionLayer:
    HARNESS = "HARNESS"
    DOM = "DOM"
    NETWORK = "NETWORK"
```

A decision of `BLOCKED` in `ENFORCE` mode halts execution and raises `IrreversibleActionBlockedError`.
