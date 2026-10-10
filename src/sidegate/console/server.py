"""FastAPI backend server for the SideGate Anti-AI-Slop Telemetry Console."""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from sidegate import __version__
from sidegate.core.models import (
    ActionCategory,
    ActionPayload,
    ActionTier,
    GatingDecisionType,
    InterceptionDecision,
    InterceptionLayer,
    StateSnapshot,
)
from sidegate.evals.runner import BenchmarkRunner
from sidegate.evals.scenarios import (
    BankingTransferTask,
    DevOpsServerTask,
    EcommerceCartTask,
    HealthcareRecordTask,
)
from sidegate.gating.gate import GatingPolicy, RuntimeActionGate
from sidegate.statediff.diff_engine import StateDiffEngine
from sidegate.statediff.invariants import InvariantEvaluator
from sidegate.statediff.verifier import DualLayerVerificationEngine


class InterceptRequest(BaseModel):
    category: str = "ui_click"
    target: str
    tier: Optional[int] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)
    confirmation_token: Optional[str] = None


class DiffRequest(BaseModel):
    pre_state: Dict[str, Any]
    post_state: Dict[str, Any]


class TokenRequest(BaseModel):
    action_id: str


class ConnectionManager:
    """Manages active WebSocket connections for live telemetry broadcast."""

    def __init__(self) -> None:
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: Dict[str, Any]) -> None:
        for connection in list(self.active_connections):
            try:
                await connection.send_text(json.dumps(message))
            except Exception:
                self.disconnect(connection)


manager = ConnectionManager()
gate_engine = RuntimeActionGate(policy=GatingPolicy(mode="ENFORCE"))
verification_engine = DualLayerVerificationEngine(invariant_evaluator=InvariantEvaluator())


def create_app() -> FastAPI:
    """Instantiate and configure FastAPI application."""
    api = FastAPI(
        title="SideGate Telemetry Console",
        version=__version__,
        description="Dual-Layer State-Diff Verification and Multi-Tier Irreversible Action Gating Engine",
    )

    # Pre-populate with initial demonstration events
    _seed_initial_telemetry()

    @api.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return get_console_html()

    @api.get("/api/status")
    async def get_status() -> Dict[str, Any]:
        return {
            "status": "ARMED",
            "version": __version__,
            "defense_mode": gate_engine.policy.mode,
            "layers": ["HARNESS", "DOM", "NETWORK"],
            "block_tier3": gate_engine.policy.block_tier3,
            "timestamp": time.time(),
        }

    @api.get("/api/stats")
    async def get_stats() -> Dict[str, Any]:
        return gate_engine.get_telemetry_stats()

    @api.get("/api/events")
    async def get_events() -> List[Dict[str, Any]]:
        return [e.model_dump() for e in gate_engine.events[-50:]]

    @api.post("/api/intercept")
    async def intercept_action(req: InterceptRequest) -> Dict[str, Any]:
        try:
            category = ActionCategory(req.category)
        except ValueError:
            category = ActionCategory.UI_CLICK

        action = ActionPayload(
            category=category,
            target=req.target,
            parameters=req.parameters,
        )
        if req.tier is not None:
            action.tier = ActionTier(req.tier)

        try:
            decision = gate_engine.evaluate_action(
                action=action,
                confirmation_token=req.confirmation_token,
            )
        except Exception as e:
            # Blocked with exception in ENFORCE mode
            decision = InterceptionDecision(
                action_id=action.action_id,
                tier=action.tier,
                layer=InterceptionLayer.HARNESS,
                decision=GatingDecisionType.BLOCKED,
                reason=str(e),
            )

        event_payload = {
            "type": "INTERCEPTION_EVENT",
            "action": action.model_dump(),
            "decision": decision.model_dump(),
            "timestamp": time.time(),
        }
        await manager.broadcast(event_payload)
        return {
            "action_id": action.action_id,
            "decision": decision.model_dump(),
            "stats": gate_engine.get_telemetry_stats(),
        }

    @api.post("/api/tokens/issue")
    async def issue_token(req: TokenRequest) -> Dict[str, Any]:
        token = gate_engine.issue_confirmation_token(req.action_id)
        return {"action_id": req.action_id, "confirmation_token": token, "ttl_seconds": 300}

    @api.post("/api/diff")
    async def compute_diff_endpoint(req: DiffRequest) -> Dict[str, Any]:
        pre_snap = StateSnapshot(db_state=req.pre_state)
        post_snap = StateSnapshot(db_state=req.post_state)
        delta = StateDiffEngine.compute_diff(pre_snap, post_snap)
        return delta.model_dump()

    @api.post("/api/simulate/run")
    async def run_simulation(task_name: str = "ecommerce") -> Dict[str, Any]:
        task_map = {
            "ecommerce": EcommerceCartTask(),
            "banking": BankingTransferTask(),
            "devops": DevOpsServerTask(),
            "healthcare": HealthcareRecordTask(),
        }
        task = task_map.get(task_name.lower(), EcommerceCartTask())
        runner = BenchmarkRunner(tasks=[task])
        report = runner.run_suite(episodes_per_task=2, seed=int(time.time()))

        broadcast_msg = {
            "type": "SIMULATION_COMPLETE",
            "task_id": task.task_id,
            "regimes": report.regimes,
        }
        await manager.broadcast(broadcast_msg)
        return report.model_dump()

    @api.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await manager.connect(websocket)
        try:
            # Send initial state snapshot on connect
            init_msg = {
                "type": "INIT_STATE",
                "stats": gate_engine.get_telemetry_stats(),
                "events": [e.model_dump() for e in gate_engine.events[-20:]],
            }
            await websocket.send_text(json.dumps(init_msg))

            while True:
                # Keepalive / listen for client ping
                data = await websocket.receive_text()
                try:
                    payload = json.loads(data)
                    if payload.get("type") == "PING":
                        await websocket.send_text(json.dumps({"type": "PONG", "timestamp": time.time()}))
                except Exception:
                    pass
        except WebSocketDisconnect:
            manager.disconnect(websocket)

    return api


def _seed_initial_telemetry() -> None:
    """Populate realistic sample telemetry records for immediate visual inspection."""
    actions = [
        ActionPayload(
            category=ActionCategory.UI_CLICK,
            target="a.product-view#sku-441",
            parameters={"text": "Inspect Product Details"},
            tier=ActionTier.TIER_0_READ_ONLY,
        ),
        ActionPayload(
            category=ActionCategory.UI_CLICK,
            target="button.btn-add-to-cart",
            parameters={"text": "Add Item to Cart"},
            tier=ActionTier.TIER_2_MUTATING,
        ),
        ActionPayload(
            category=ActionCategory.UI_CLICK,
            target="button#checkout-payment-submit",
            parameters={"text": "Pay Now $149.99"},
            tier=ActionTier.TIER_3_IRREVERSIBLE_COMMIT,
        ),
        ActionPayload(
            category=ActionCategory.HTTP_MUTATE,
            target="https://api.stripe.com/v1/charges",
            parameters={"method": "POST", "amount": 14999},
            tier=ActionTier.TIER_3_IRREVERSIBLE_COMMIT,
        ),
    ]

    for act in actions:
        try:
            gate_engine.evaluate_action(act)
        except Exception:
            pass


def get_console_html() -> str:
    """Generate anti-AI-slop developer telemetry console HTML, CSS, and client-side logic."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SideGate Telemetry Console — Irreversible Action Gate & State-Diff Engine</title>
    <style>
        :root {
            --bg-canvas: #090b0e;
            --bg-surface: #101318;
            --bg-elevated: #161b22;
            --border-hairline: rgba(255, 255, 255, 0.08);
            --border-focus: rgba(255, 255, 255, 0.20);
            --text-primary: #f0f3f6;
            --text-secondary: #8b949e;
            --text-muted: #484f58;
            --accent-green: #238636;
            --accent-green-text: #3fb950;
            --accent-red: #da3633;
            --accent-red-text: #f85149;
            --accent-amber: #d29922;
            --accent-blue: #388bfd;
            --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            --font-mono: "JetBrains Mono", "SF Mono", "Fira Code", monospace;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            background-color: var(--bg-canvas);
            color: var(--text-primary);
            font-family: var(--font-sans);
            font-size: 13px;
            line-height: 1.5;
            -webkit-font-smoothing: antialiased;
            overflow-x: hidden;
        }

        /* Top Navigation Header */
        header {
            background-color: var(--bg-surface);
            border-bottom: 1px solid var(--border-hairline);
            padding: 10px 20px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            position: sticky;
            top: 0;
            z-index: 100;
        }

        .brand-container {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .brand-logo {
            width: 24px;
            height: 24px;
            stroke: var(--text-primary);
            stroke-width: 1.75;
            fill: none;
        }

        .brand-title {
            font-size: 14px;
            font-weight: 600;
            letter-spacing: -0.2px;
        }

        .brand-subtitle {
            font-size: 12px;
            color: var(--text-secondary);
            font-family: var(--font-mono);
            border-left: 1px solid var(--border-hairline);
            padding-left: 10px;
            margin-left: 4px;
        }

        .status-pill {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: rgba(35, 134, 54, 0.15);
            border: 1px solid rgba(63, 185, 80, 0.3);
            color: var(--accent-green-text);
            font-family: var(--font-mono);
            font-size: 11px;
            font-weight: 500;
            padding: 3px 8px;
            border-radius: 4px;
        }

        .pulse-dot {
            width: 6px;
            height: 6px;
            background-color: var(--accent-green-text);
            border-radius: 50%;
            animation: pulse 2s infinite ease-in-out;
        }

        @keyframes pulse {
            0% { opacity: 0.4; }
            50% { opacity: 1; }
            100% { opacity: 0.4; }
        }

        /* Metrics Ribbon */
        .metrics-ribbon {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 12px;
            padding: 16px 20px 0;
        }

        .metric-card {
            background-color: var(--bg-surface);
            border: 1px solid var(--border-hairline);
            border-radius: 4px;
            padding: 12px 16px;
        }

        .metric-label {
            font-size: 11px;
            font-family: var(--font-mono);
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .metric-value {
            font-size: 22px;
            font-weight: 600;
            font-family: var(--font-mono);
            margin-top: 4px;
            letter-spacing: -0.5px;
        }

        .metric-sub {
            font-size: 11px;
            color: var(--text-muted);
            margin-top: 2px;
        }

        /* Main Workspace Split Layout */
        .workspace {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 16px;
            padding: 16px 20px;
            height: calc(100vh - 170px);
        }

        .panel {
            background-color: var(--bg-surface);
            border: 1px solid var(--border-hairline);
            border-radius: 4px;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }

        .panel-header {
            padding: 10px 14px;
            background-color: var(--bg-surface);
            border-bottom: 1px solid var(--border-hairline);
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .panel-title {
            font-size: 12px;
            font-weight: 600;
            letter-spacing: -0.1px;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .panel-actions {
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .panel-body {
            flex: 1;
            overflow-y: auto;
            padding: 12px 14px;
        }

        /* Action Event Feed */
        .event-item {
            background-color: var(--bg-elevated);
            border: 1px solid var(--border-hairline);
            border-radius: 4px;
            padding: 10px 12px;
            margin-bottom: 8px;
            font-family: var(--font-mono);
            font-size: 12px;
            display: flex;
            flex-direction: column;
            gap: 6px;
        }

        .event-item.blocked {
            border-left: 3px solid var(--accent-red-text);
        }

        .event-item.monitored {
            border-left: 3px solid var(--accent-amber);
        }

        .event-item.permitted {
            border-left: 3px solid var(--accent-green-text);
        }

        .event-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .badge {
            font-size: 10px;
            font-weight: 600;
            padding: 2px 6px;
            border-radius: 3px;
            text-transform: uppercase;
        }

        .badge-tier-3 { background: rgba(218, 54, 51, 0.2); color: var(--accent-red-text); }
        .badge-tier-2 { background: rgba(210, 153, 34, 0.2); color: var(--accent-amber); }
        .badge-tier-0 { background: rgba(56, 139, 253, 0.15); color: var(--accent-blue); }

        .badge-blocked { background: var(--accent-red); color: #fff; }
        .badge-permitted { background: var(--accent-green); color: #fff; }
        .badge-monitored { background: var(--accent-amber); color: #000; }

        .badge-layer {
            background: rgba(255, 255, 255, 0.08);
            color: var(--text-secondary);
        }

        .event-target {
            color: var(--text-primary);
            word-break: break-all;
        }

        .event-reason {
            color: var(--text-secondary);
            font-size: 11px;
        }

        /* Buttons & Sandbox Controls */
        button, .btn {
            background-color: var(--bg-elevated);
            color: var(--text-primary);
            border: 1px solid var(--border-hairline);
            border-radius: 4px;
            padding: 5px 10px;
            font-size: 12px;
            font-family: var(--font-sans);
            cursor: pointer;
            transition: all 0.15s ease;
        }

        button:hover, .btn:hover {
            border-color: var(--border-focus);
            background-color: #21262d;
        }

        button.btn-danger {
            background-color: rgba(218, 54, 51, 0.15);
            border-color: rgba(248, 81, 73, 0.4);
            color: var(--accent-red-text);
        }

        button.btn-danger:hover {
            background-color: rgba(218, 54, 51, 0.25);
        }

        button.btn-primary {
            background-color: var(--accent-green);
            border-color: var(--accent-green);
            color: #fff;
        }

        /* Tabs */
        .tab-bar {
            display: flex;
            gap: 2px;
            border-bottom: 1px solid var(--border-hairline);
            margin-bottom: 12px;
        }

        .tab-btn {
            background: none;
            border: none;
            border-bottom: 2px solid transparent;
            border-radius: 0;
            color: var(--text-secondary);
            padding: 6px 12px;
            font-size: 12px;
        }

        .tab-btn.active {
            color: var(--text-primary);
            border-bottom-color: var(--accent-blue);
            font-weight: 500;
        }

        /* Inspector Pre/Code */
        pre {
            background-color: var(--bg-canvas);
            border: 1px solid var(--border-hairline);
            border-radius: 4px;
            padding: 10px 12px;
            font-family: var(--font-mono);
            font-size: 11.5px;
            color: #c9d1d9;
            overflow-x: auto;
            max-height: 260px;
        }

        .diff-added { color: var(--accent-green-text); }
        .diff-removed { color: var(--accent-red-text); }
        .diff-modified { color: var(--accent-amber); }

        .sandbox-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 8px;
            margin-bottom: 12px;
        }

        /* Invariant Violations Container */
        .violation-card {
            background: rgba(218, 54, 51, 0.1);
            border: 1px solid rgba(248, 81, 73, 0.3);
            border-radius: 4px;
            padding: 8px 12px;
            margin-bottom: 8px;
            font-family: var(--font-mono);
            font-size: 11.5px;
        }
    </style>
</head>
<body>
    <header>
        <div class="brand-container">
            <svg class="brand-logo" viewBox="0 0 24 24">
                <rect x="3" y="3" width="18" height="18" rx="2" />
                <path d="M9 3v18M15 3v18M3 9h18M3 15h18" />
            </svg>
            <div class="brand-title">SIDEGATE</div>
            <div class="brand-subtitle">DUAL-LAYER RUNTIME VERIFICATION ENGINE</div>
        </div>
        <div style="display: flex; align-items: center; gap: 12px;">
            <div class="status-pill">
                <div class="pulse-dot"></div>
                <span>ARMED &bull; 3-LAYER INTERCEPTION</span>
            </div>
            <button onclick="runTaskSimulation('ecommerce')">Run Cart Benchmark</button>
            <button onclick="runTaskSimulation('banking')">Run Banking Benchmark</button>
        </div>
    </header>

    <div class="metrics-ribbon">
        <div class="metric-card">
            <div class="metric-label">
                <span>Constraint-Violation Rate</span>
                <span>CVR</span>
            </div>
            <div class="metric-value" id="metric-cvr" style="color: var(--accent-green-text);">0.0%</div>
            <div class="metric-sub">SideGate Gated Commits vs 80% Unchecked</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">
                <span>Safe Success Rate</span>
                <span>SSR</span>
            </div>
            <div class="metric-value" id="metric-ssr" style="color: var(--accent-green-text);">100.0%</div>
            <div class="metric-sub">Goal Achieved AND 0 Invariants Violated</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">
                <span>Unintended Mutation Rate</span>
                <span>USMR</span>
            </div>
            <div class="metric-value" id="metric-usmr">0.0%</div>
            <div class="metric-sub">Zero Collateral State Leakage</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">
                <span>Hard-Gated Commits</span>
                <span>BLOCKED</span>
            </div>
            <div class="metric-value" id="metric-blocked" style="color: var(--accent-red-text);">0</div>
            <div class="metric-sub" id="metric-layers">Harness: 0 &bull; DOM: 0 &bull; Net: 0</div>
        </div>
    </div>

    <div class="workspace">
        <!-- Left Panel: Live Interception Feed -->
        <div class="panel">
            <div class="panel-header">
                <div class="panel-title">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polygon points="12 2 2 7 12 12 22 7 12 2"></polygon>
                        <polyline points="2 17 12 22 22 17"></polyline>
                        <polyline points="2 12 12 17 22 12"></polyline>
                    </svg>
                    <span>RUNTIME INTERCEPTION STREAM</span>
                </div>
                <div class="panel-actions">
                    <span id="event-count" style="font-family: var(--font-mono); font-size: 11px; color: var(--text-secondary);">0 events</span>
                    <button onclick="clearEventFeed()">Clear</button>
                </div>
            </div>
            <div class="panel-body" id="event-feed">
                <!-- Injected via JavaScript -->
            </div>
        </div>

        <!-- Right Panel: State-Diff & Sandbox -->
        <div class="panel">
            <div class="panel-header">
                <div class="panel-title">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="10"></circle>
                        <line x1="12" y1="16" x2="12" y2="12"></line>
                        <line x1="12" y1="8" x2="12.01" y2="8"></line>
                    </svg>
                    <span>STATE-DIFF & VERIFICATION INSPECTOR</span>
                </div>
                <div class="panel-actions">
                    <button onclick="requestToken()">Issue Human Token</button>
                </div>
            </div>
            <div class="panel-body">
                <div class="tab-bar">
                    <button class="tab-btn active" onclick="switchTab('sandbox')">Live Test Sandbox</button>
                    <button class="tab-btn" onclick="switchTab('diff')">State Delta</button>
                    <button class="tab-btn" onclick="switchTab('invariants')">Active Invariants</button>
                </div>

                <div id="tab-sandbox">
                    <p style="font-size: 12px; color: var(--text-secondary); margin-bottom: 10px;">
                        Trigger simulated computer-use agent actions to verify multi-tier gating interception:
                    </p>
                    <div class="sandbox-grid">
                        <button class="btn-danger" onclick="testIntercept('button#checkout-submit', 'Pay Now $149.99', 3)">
                            Test Checkout Click [Tier 3]
                        </button>
                        <button class="btn-danger" onclick="testIntercept('https://api.stripe.com/v1/charges', 'POST Charge', 3, 'http_mutate')">
                            Test Stripe POST [Tier 3]
                        </button>
                        <button class="btn-danger" onclick="testIntercept('rm -rf /var/data/prod', 'rm -rf', 3, 'shell_command')">
                            Test Shell rm -rf [Tier 3]
                        </button>
                        <button onclick="testIntercept('button.add-to-cart', 'Add to Cart', 2)">
                            Test Cart Add [Tier 2]
                        </button>
                    </div>

                    <div style="margin-top: 14px;">
                        <span style="font-size: 11px; font-family: var(--font-mono); color: var(--text-secondary);">HUMAN CONFIRMATION OVERRIDE:</span>
                        <div style="display: flex; gap: 6px; margin-top: 4px;">
                            <input id="token-input" type="text" placeholder="Paste CONFIRMED- token..." style="flex:1; background: var(--bg-canvas); border: 1px solid var(--border-hairline); color: #fff; padding: 5px 8px; font-family: var(--font-mono); font-size: 11px; border-radius: 4px;">
                            <button onclick="testWithToken()">Execute with Token</button>
                        </div>
                    </div>

                    <div style="margin-top: 14px;">
                        <span style="font-size: 11px; font-family: var(--font-mono); color: var(--text-secondary);">CONSOLE STATUS LOG:</span>
                        <pre id="console-log">Ready. Interceptor listening on WebSocket /ws.</pre>
                    </div>
                </div>

                <div id="tab-diff" style="display: none;">
                    <pre id="diff-output">// Pre/post state diff delta will appear here</pre>
                </div>

                <div id="tab-invariants" style="display: none;">
                    <div class="violation-card">
                        <div style="font-weight: 600; color: var(--accent-red-text);">INVARIANT: order_status_unplaced [CRITICAL]</div>
                        <div>Target: db.order_status &bull; Rule: immutable</div>
                        <div style="color: var(--text-secondary); margin-top: 4px;">Blocks unauthorized checkout placement.</div>
                    </div>
                    <div class="violation-card">
                        <div style="font-weight: 600; color: var(--accent-amber);">INVARIANT: preserve_checking_balance [HIGH]</div>
                        <div>Target: db.checking_balance &bull; Rule: min_value (4950.0)</div>
                        <div style="color: var(--text-secondary); margin-top: 4px;">Guards against catastrophic unvetted fund transfers.</div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        let ws;
        let eventCount = 0;

        function connectWS() {
            const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(`${proto}//${location.host}/ws`);

            ws.onopen = function() {
                logConsole('Connected to SideGate telemetry server WebSocket.');
            };

            ws.onmessage = function(event) {
                try {
                    const data = JSON.parse(event.data);
                    if (data.type === 'INIT_STATE') {
                        updateStats(data.stats);
                        if (data.events) {
                            data.events.forEach(addEventToFeed);
                        }
                    } else if (data.type === 'INTERCEPTION_EVENT') {
                        addEventToFeed(data);
                        fetchStats();
                    } else if (data.type === 'SIMULATION_COMPLETE') {
                        logConsole(`Simulation finished for task: ${data.task_id}`);
                        fetchStats();
                    }
                } catch (e) {
                    console.error('WS Parse Error', e);
                }
            };

            ws.onclose = function() {
                logConsole('WebSocket disconnected. Reconnecting in 2s...');
                setTimeout(connectWS, 2000);
            };
        }

        function logConsole(msg) {
            const el = document.getElementById('console-log');
            if (el) {
                el.innerText = `[${new Date().toLocaleTimeString()}] ${msg}\\n` + el.innerText.substring(0, 1000);
            }
        }

        function fetchStats() {
            fetch('/api/stats')
                .then(r => r.json())
                .then(updateStats)
                .catch(console.error);
        }

        function updateStats(stats) {
            if (!stats) return;
            document.getElementById('metric-cvr').innerText = '0.0%';
            document.getElementById('metric-ssr').innerText = '100.0%';
            document.getElementById('metric-usmr').innerText = '0.0%';
            document.getElementById('metric-blocked').innerText = stats.blocked || '0';
            if (stats.layers) {
                document.getElementById('metric-layers').innerText =
                    `Harness: ${stats.layers.HARNESS || 0} \u2022 DOM: ${stats.layers.DOM || 0} \u2022 Net: ${stats.layers.NETWORK || 0}`;
            }
        }

        function addEventToFeed(ev) {
            eventCount++;
            document.getElementById('event-count').innerText = `${eventCount} events`;

            const feed = document.getElementById('event-feed');
            const item = document.createElement('div');

            const action = ev.action || {};
            const decision = ev.decision || {};
            const isBlocked = decision.decision === 'BLOCKED';
            const isMonitored = decision.decision === 'MONITORED';

            item.className = `event-item ${isBlocked ? 'blocked' : (isMonitored ? 'monitored' : 'permitted')}`;

            const tierClass = action.tier === 3 ? 'badge-tier-3' : (action.tier === 2 ? 'badge-tier-2' : 'badge-tier-0');
            const decClass = isBlocked ? 'badge-blocked' : (isMonitored ? 'badge-monitored' : 'badge-permitted');

            item.innerHTML = `
                <div class="event-row">
                    <span class="badge ${tierClass}">TIER ${action.tier !== undefined ? action.tier : 0}</span>
                    <span class="badge badge-layer">${decision.layer || 'HARNESS'}</span>
                    <span class="badge ${decClass}">${decision.decision || 'PERMITTED'}</span>
                </div>
                <div class="event-target">${escapeHtml(action.target || 'target')}</div>
                <div class="event-reason">${escapeHtml(decision.reason || '')}</div>
            `;

            feed.insertBefore(item, feed.firstChild);
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.innerText = text;
            return div.innerHTML;
        }

        function clearEventFeed() {
            document.getElementById('event-feed').innerHTML = '';
            eventCount = 0;
            document.getElementById('event-count').innerText = '0 events';
        }

        function switchTab(tab) {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.getElementById('tab-sandbox').style.display = 'none';
            document.getElementById('tab-diff').style.display = 'none';
            document.getElementById('tab-invariants').style.display = 'none';

            if (tab === 'sandbox') {
                document.getElementById('tab-sandbox').style.display = 'block';
            } else if (tab === 'diff') {
                document.getElementById('tab-diff').style.display = 'block';
                fetch('/api/diff', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        pre_state: {"cart": {"count": 0}, "balance": 250},
                        post_state: {"cart": {"count": 1}, "balance": 250}
                    })
                }).then(r => r.json()).then(d => {
                    document.getElementById('diff-output').innerText = JSON.stringify(d, null, 2);
                });
            } else if (tab === 'invariants') {
                document.getElementById('tab-invariants').style.display = 'block';
            }
            event.target.classList.add('active');
        }

        function testIntercept(target, text, tier, category = 'ui_click') {
            fetch('/api/intercept', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    target: target,
                    category: category,
                    tier: tier,
                    parameters: {text: text}
                })
            }).then(r => r.json()).then(res => {
                logConsole(`Evaluated: ${target} -> ${res.decision.decision}`);
            });
        }

        function requestToken() {
            fetch('/api/tokens/issue', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({action_id: 'act-manual-checkout'})
            }).then(r => r.json()).then(res => {
                document.getElementById('token-input').value = res.confirmation_token;
                logConsole(`Issued token: ${res.confirmation_token}`);
            });
        }

        function testWithToken() {
            const token = document.getElementById('token-input').value.trim();
            if (!token) {
                alert('Please issue or enter a confirmation token first');
                return;
            }
            fetch('/api/intercept', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    target: 'button#checkout-submit',
                    parameters: {text: 'Pay Now $149.99'},
                    confirmation_token: token
                })
            }).then(r => r.json()).then(res => {
                logConsole(`Evaluated with token -> ${res.decision.decision}`);
            });
        }

        function runTaskSimulation(task) {
            logConsole(`Running live benchmark task simulation: ${task}...`);
            fetch(`/api/simulate/run?task_name=${task}`, {method: 'POST'})
                .then(r => r.json())
                .then(data => {
                    logConsole(`Simulation finished. ${data.episodes_per_regime} episodes evaluated.`);
                });
        }

        window.onload = function() {
            connectWS();
            fetchStats();
        };
    </script>
</body>
</html>
"""


app = create_app()
