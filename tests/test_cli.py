"""Unit tests for SideGate Typer CLI."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from sidegate import __version__
from sidegate.cli.main import app

runner = CliRunner()


def test_cli_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "SIDEGATE SYSTEM TELEMETRY" in result.stdout
    assert f"v{__version__}" in result.stdout


def test_cli_policy():
    result = runner.invoke(app, ["policy"])
    assert result.exit_code == 0
    assert "SideGate Active Policy Rules" in result.stdout
    assert "DOM Layer" in result.stdout
    assert "HARD BLOCK" in result.stdout


def test_cli_run_ecommerce():
    result = runner.invoke(app, ["run", "--task", "ecommerce"])
    assert result.exit_code == 0
    assert "Executing Episode: E-Commerce Shopping Cart Isolation" in result.stdout
    assert "POST-ACTION STATE-DIFF AUDIT" in result.stdout


def test_cli_eval():
    result = runner.invoke(app, ["eval", "--episodes", "1", "--seed", "42"])
    assert result.exit_code == 0
    assert "Comparative Evaluation Matrix" in result.stdout
    assert "SideGate Dual-Layer" in result.stdout


def test_cli_diff(tmp_path: Path):
    pre_path = tmp_path / "pre.json"
    post_path = tmp_path / "post.json"

    pre_path.write_text(json.dumps({"counter": 10, "unchanged": True}))
    post_path.write_text(json.dumps({"counter": 20, "added_key": "val", "unchanged": True}))

    result = runner.invoke(app, ["diff", str(pre_path), str(post_path)])
    assert result.exit_code == 0
    assert "State Delta" in result.stdout
    assert "counter" in result.stdout
    assert "added_key" in result.stdout


def test_cli_eval_export(tmp_path: Path):
    export_json = tmp_path / "benchmark.json"
    export_md = tmp_path / "benchmark.md"

    res_json = runner.invoke(app, ["eval", "--episodes", "1", "--export", str(export_json)])
    assert res_json.exit_code == 0
    assert export_json.exists()
    data = json.loads(export_json.read_text())
    assert "regimes" in data

    res_md = runner.invoke(app, ["eval", "--episodes", "1", "--export", str(export_md)])
    assert res_md.exit_code == 0
    assert export_md.exists()
    assert "SideGate Benchmark Suite Report" in export_md.read_text()


def test_cli_diff_with_invariants(tmp_path: Path):
    pre_path = tmp_path / "pre.json"
    post_path = tmp_path / "post.json"
    inv_path = tmp_path / "inv.json"

    pre_path.write_text(json.dumps({"account": {"balance": 100.0}}))
    post_path.write_text(json.dumps({"account": {"balance": 40.0}}))
    inv_path.write_text(json.dumps([
        {
            "name": "min_balance",
            "description": "Balance min 50",
            "domain": "database",
            "target_path": "db.account.balance",
            "rule_type": "min_value",
            "constraint_param": 50.0,
            "severity": "CRITICAL",
        }
    ]))

    result = runner.invoke(app, ["diff", str(pre_path), str(post_path), "--invariants", str(inv_path)])
    assert result.exit_code == 0
    assert "Detected Invariant Violations" in result.stdout
    assert "min_balance" in result.stdout
