"""Command-line interface for SideGate runtime verification and benchmark suite."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from sidegate import __version__
from sidegate.core.models import (
    GatingDecisionType,
    StateSnapshot,
)
from sidegate.evals.runner import BenchmarkRunner
from sidegate.evals.scenarios import (
    BankingTransferTask,
    DevOpsServerTask,
    EcommerceCartTask,
    HealthcareRecordTask,
    get_standard_benchmark_suite,
)
from sidegate.gating.gate import GatingPolicy, RuntimeActionGate
from sidegate.statediff.diff_engine import StateDiffEngine
from sidegate.statediff.invariants import InvariantEvaluator
from sidegate.statediff.verifier import DualLayerVerificationEngine

app = typer.Typer(
    name="sidegate",
    help="Dual-Layer State-Diff Verification and Multi-Tier Irreversible Action Gating Engine.",
    no_args_is_help=True,
)
console = Console()


@app.command("version")
def version_cmd() -> None:
    """Display SideGate framework version and defense layer status."""
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold cyan")
    grid.add_column()
    grid.add_row("SideGate Engine Version:", f"v{__version__}")
    grid.add_row("Architecture Layers:", "Dual-Layer (Runtime Gate + State-Diff Audit)")
    grid.add_row("Interception Boundaries:", "Harness Layer, DOM Layer, Network Proxy Layer")
    grid.add_row("Safety Standard:", "Zero-Tolerance Irreversible Commit Gating")

    panel = Panel(
        grid,
        title="[bold white]SIDEGATE SYSTEM TELEMETRY[/bold white]",
        border_style="bright_blue",
        box=box.ROUNDED,
    )
    console.print(panel)


@app.command("eval")
def eval_cmd(
    episodes: int = typer.Option(3, "--episodes", "-n", help="Episodes per task scenario"),
    seed: int = typer.Option(42, "--seed", "-s", help="Random seed for reproducibility"),
    markdown: bool = typer.Option(False, "--markdown", "-m", help="Output as Markdown table"),
) -> None:
    """Run comprehensive benchmark suite comparing baseline, prompt-only, outcome-only, and SideGate regimes."""
    console.print(
        f"[bold cyan]Running SideGate Benchmark Suite[/bold cyan] (Episodes: {episodes}, Seed: {seed})...\n"
    )

    tasks = get_standard_benchmark_suite()
    runner = BenchmarkRunner(tasks=tasks)
    report = runner.run_suite(episodes_per_task=episodes, seed=seed)

    if markdown:
        console.print(report.to_markdown_table())
        return

    table = Table(
        title="Comparative Evaluation Matrix: Agent Safety & State Integrity",
        box=box.ROUNDED,
        header_style="bold cyan",
    )
    table.add_column("Defense Regime", style="bold white", min_width=28)
    table.add_column("Success Rate", justify="right")
    table.add_column("CVR", justify="right", style="bold red")
    table.add_column("Safe SSR", justify="right", style="bold green")
    table.add_column("USMR", justify="right", style="yellow")
    table.add_column("Blocked Commits", justify="right")

    for r in report.regimes:
        cvr_color = "green" if r["constraint_violation_rate"] == 0.0 else "red"
        table.add_row(
            r["regime"],
            f"{r['task_success_rate'] * 100:.1f}%",
            f"[{cvr_color}]{r['constraint_violation_rate'] * 100:.1f}%[/{cvr_color}]",
            f"{r['safe_success_rate'] * 100:.1f}%",
            f"{r['unintended_mutation_rate'] * 100:.1f}%",
            str(r["blocked_commits"]),
        )

    console.print(table)


@app.command("run")
def run_cmd(
    task: str = typer.Option("ecommerce", "--task", "-t", help="Task name: ecommerce, banking, devops, healthcare"),
    bypass_token: Optional[str] = typer.Option(None, "--token", help="Confirmation token for human override"),
) -> None:
    """Run a single task episode through the Irreversible Action Gate with real-time audit."""
    task_map = {
        "ecommerce": EcommerceCartTask(),
        "banking": BankingTransferTask(),
        "devops": DevOpsServerTask(),
        "healthcare": HealthcareRecordTask(),
    }
    selected_task = task_map.get(task.lower())
    if not selected_task:
        console.print(f"[red]Error:[/red] Unknown task '{task}'. Choose: ecommerce, banking, devops, healthcare")
        raise typer.Exit(1)

    console.print(f"[bold cyan]Executing Episode:[/bold cyan] {selected_task.name}")
    console.print(f"[dim]{selected_task.prompt}[/dim]\n")

    gate = RuntimeActionGate(policy=GatingPolicy(mode="ENFORCE"))
    verifier = DualLayerVerificationEngine(
        invariant_evaluator=InvariantEvaluator(selected_task.get_invariants())
    )

    pre_state = selected_task.get_initial_state()
    current_state = selected_task.get_initial_state()
    actions = selected_task.get_candidate_actions()

    table = Table(title="Step-by-Step Interception Trace", box=box.SIMPLE_HEAVY)
    table.add_column("Step", style="dim", width=6)
    table.add_column("Category", style="cyan")
    table.add_column("Target Selector / Path", style="white")
    table.add_column("Tier", justify="center")
    table.add_column("Gate Verdict", justify="center")
    table.add_column("Reason / Detail", style="dim")

    interception_events = []

    for idx, act in enumerate(actions, 1):
        tier = gate.classifier.classify(act)
        try:
            decision = gate.evaluate_action(act, confirmation_token=bypass_token)
            verdict_str = f"[green]{decision.decision.value}[/green]"
            current_state = selected_task.apply_action(current_state, act)
        except Exception as e:
            verdict_str = "[red]BLOCKED[/red]"
            decision = gate.dom.evaluate_click(act.target)
            decision.decision = GatingDecisionType.BLOCKED
            decision.reason = str(e)

        table.add_row(
            str(idx),
            act.category.value,
            act.target,
            f"T{tier.value}",
            verdict_str,
            decision.reason,
        )

    console.print(table)
    console.print()

    audit = verifier.audit(
        task_id=selected_task.task_id,
        pre_snapshot=pre_state,
        post_snapshot=current_state,
        goal_predicates=selected_task.get_goal_predicates(),
        interception_events=interception_events,
    )

    audit_panel = Panel(
        f"[bold]Goal Achieved:[/bold] {audit.goal_achieved}\n"
        f"[bold]Safe Success (SSR):[/bold] {audit.safe_success}\n"
        f"[bold]Total State Mutations:[/bold] {audit.total_mutations} "
        f"(Intended: {audit.intended_mutations}, Unintended: {audit.unintended_mutations})\n"
        f"[bold]Violations Detected:[/bold] {len(audit.violations)}",
        title="[bold white]POST-ACTION STATE-DIFF AUDIT[/bold white]",
        border_style="green" if audit.safe_success else "red",
        box=box.ROUNDED,
    )
    console.print(audit_panel)


@app.command("diff")
def diff_cmd(
    pre_file: Path = typer.Argument(..., help="Path to pre-state JSON snapshot"),
    post_file: Path = typer.Argument(..., help="Path to post-state JSON snapshot"),
) -> None:
    """Compute and display deep structural delta between two JSON snapshot files."""
    if not pre_file.exists() or not post_file.exists():
        console.print("[red]Error:[/red] One or both snapshot files do not exist.")
        raise typer.Exit(1)

    pre_data = json.loads(pre_file.read_text())
    post_data = json.loads(post_file.read_text())

    pre_snap = StateSnapshot(db_state=pre_data)
    post_snap = StateSnapshot(db_state=post_data)

    delta = StateDiffEngine.compute_diff(pre_snap, post_snap)

    table = Table(title=f"State Delta: {pre_file.name} vs {post_file.name}", box=box.ROUNDED)
    table.add_column("Domain", style="cyan")
    table.add_column("Mutation Type", justify="center")
    table.add_column("State Path", style="bold white")
    table.add_column("Old Value", style="red")
    table.add_column("New Value", style="green")

    for m in delta.mutations:
        table.add_row(
            m.domain.value,
            m.mutation_type.value,
            m.path,
            str(m.old_value) if m.old_value is not None else "[dim]null[/dim]",
            str(m.new_value) if m.new_value is not None else "[dim]null[/dim]",
        )

    console.print(table)
    console.print(f"[dim]Total Mutations: {delta.total_mutations} | Checksum: {delta.checksum[:16]}...[/dim]")


@app.command("serve")
def serve_cmd(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Bind host address"),
    port: int = typer.Option(8090, "--port", "-p", help="Bind port"),
) -> None:
    """Launch the SideGate Anti-AI-Slop Telemetry Console server."""
    import uvicorn
    console.print(f"[bold cyan]Launching SideGate Telemetry Console[/bold cyan] at http://{host}:{port}/")
    uvicorn.run("sidegate.console.server:app", host=host, port=port, reload=False)


@app.command("policy")
def policy_cmd() -> None:
    """Display active multi-tier action gating policy rules and defense layers."""
    table = Table(title="SideGate Active Policy Rules", box=box.ROUNDED)
    table.add_column("Defense Layer", style="cyan")
    table.add_column("Intercepted Targets / Patterns", style="white")
    table.add_column("Default Safety Tier", justify="center")
    table.add_column("Enforcement Action", style="bold red")

    table.add_row("DOM Layer", "checkout, pay now, complete purchase, #pay-button", "Tier 3", "HARD BLOCK / CLICK PREVENT")
    table.add_row("Network Layer", "api.stripe.com/charges, /orders/confirm, /transfers", "Tier 3", "EGRESS ROUTE ABORT")
    table.add_row("Harness Layer", "rm -rf, git push --force, terminate-instances, DROP TABLE", "Tier 3", "TOOL EXECUTION HALT")
    table.add_row("State-Diff Layer", "db.account.balance < min, patient.chart immutable", "All Tiers", "INVARIANT VIOLATION AUDIT")

    console.print(table)


if __name__ == "__main__":
    app()
