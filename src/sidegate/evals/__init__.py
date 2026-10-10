"""SideGate Benchmark Evaluation and Safety Metrics Suite."""

from sidegate.evals.metrics import (
    aggregate_regime_summary,
    calculate_cvr,
    calculate_ssr,
    calculate_usmr,
)
from sidegate.evals.runner import BenchmarkRunner, BenchmarkSuiteReport
from sidegate.evals.scenarios import (
    BankingTransferTask,
    DevOpsServerTask,
    EcommerceCartTask,
    HealthcareRecordTask,
    get_standard_benchmark_suite,
)

__all__ = [
    "BankingTransferTask",
    "BenchmarkRunner",
    "BenchmarkSuiteReport",
    "DevOpsServerTask",
    "EcommerceCartTask",
    "HealthcareRecordTask",
    "aggregate_regime_summary",
    "calculate_cvr",
    "calculate_ssr",
    "calculate_usmr",
    "get_standard_benchmark_suite",
]
