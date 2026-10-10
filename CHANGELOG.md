# Changelog

All notable changes to SideGate will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.2.0] - 2026-10-10

### Added
- Fine-grained recursive list diffing in `StateDiffEngine` with identity key reconciliation (`id`, `sku`, `uuid`) and positional indexing.
- Direct financial impact and side-effect leakage quantification across `StateMutation`, `StateDelta`, and `DualLayerAuditResult`.
- Monotonic non-decreasing (`no_decrease`), non-increasing (`no_increase`), and maximum deviation (`max_delta`) invariant rules.
- Declarative invariant factory constructors: `create_balance_invariant`, `create_immutable_invariant`, `create_spend_limit_invariant`.
- Active async and sync Playwright page attachment and route abort hooks: `attach_page`, `attach_page_sync`, `safe_click`, and `safe_click_sync`.
- Wilson score 95% confidence interval calculations for empirical CVR and SSR safety metrics.
- CLI report export capability (`sidegate eval --export <path.json|path.md>`) and invariant evaluation in `sidegate diff --invariants <inv.json>`.

---

## [0.1.0] - 2026-10-10

### Added
- Core domain protocols: ActionTier (T0-T3), ActionPayload, StateSnapshot, StateDelta, Invariant, GoalPredicate, ConstraintViolation.
- Deterministic canonical SHA-256 state hashing utility.
- ActionTierClassifier with heuristic pattern rules across DOM selectors, bash commands, and HTTP paths.
- Three-layer defense triad: HarnessInterceptor, DOMInterceptor with client guard script generator, and NetworkInterceptor with egress endpoint filter.
- RuntimeActionGate coordinator managing policies, cryptographic confirmation tokens, and telemetry aggregation.
- Deep recursive StateDiffEngine computing atomic additions, deletions, and modifications.
- InvariantEvaluator supporting rules: immutable, no_delete, min_value, max_value, pattern_match, and allowed_values.
- DualLayerVerificationEngine evaluating goal predicates against state deltas and computing Constraint-Violation Rate (CVR) and Safe Success Rate (SSR).
- Standard benchmark task scenarios: EcommerceCartTask, BankingTransferTask, DevOpsServerTask, and HealthcareRecordTask.
- BenchmarkRunner evaluating four defense regimes: Baseline, System Prompt Only, Outcome-Only, and SideGate Dual-Layer.
- Drop-in ecosystem adapters for Anthropic Computer Use, Playwright, and OpenAI function calling.
- Anti-AI-slop telemetry developer console with FastAPI backend, WebSocket live streaming, split-pane inspector, and test sandbox.
- Typer CLI with `sidegate run`, `sidegate eval`, `sidegate diff`, `sidegate serve`, and `sidegate policy`.
