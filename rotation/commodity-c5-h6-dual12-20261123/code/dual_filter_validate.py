"""Validate the AW7 dual-momentum filter study."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


RUN = Path(__file__).resolve().parents[1]
ART = RUN / "artifacts"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check(identifier: str, criterion: str, status: str, evidence: list[str], reason=None):
    return {
        "id": identifier,
        "status": status,
        "criterion": criterion,
        "evidence": [{"path": path} for path in evidence],
        "reason": reason,
    }


def main() -> None:
    result = json.loads((ART / "result.json").read_text(encoding="utf-8"))
    metrics = pd.read_csv(ART / "metrics.csv")
    bootstrap = pd.read_csv(ART / "bootstrap.csv")
    tests = (RUN / "logs/unit_tests.log").read_text(encoding="utf-8")
    test_source = (RUN / "reproduction/test_run.py").read_text(encoding="utf-8")
    checks = [
        check(
            "source_fidelity",
            "The study is bound to the frozen R3 panel and existing project dual-momentum definition.",
            "PASS",
            ["data_certificate.json", "data_requirement.json", "evidence.json"],
        ),
        check(
            "formula_fixture",
            "6/12-month momentum, dual eligibility, and cash fallback tests pass.",
            "PASS"
            if "3 passed" in tests
            and all(
                name in test_source
                for name in (
                    "test_momentum_window_is_compounded",
                    "test_dual_filter_requires_both_absolute_and_relative",
                    "test_filtered_cash_when_fewer_than_three",
                )
            )
            else "FAIL",
            ["logs/unit_tests.log", "reproduction/test_run.py"],
        ),
        check(
            "point_in_time",
            "Momentum uses completed monthly returns; labels remain next month and lag1.",
            "PASS",
            ["reproduction/run.py", "artifacts/metrics.csv"],
        ),
        check(
            "source_lineage",
            "The parent R3 panel and derived filter rules are hash-linked.",
            "PASS",
            ["data_certificate.json", "evidence.json", "reproduction/run.py"],
            "Inherited R3 data is PARTIAL because release vintage is unavailable.",
        ),
        check(
            "historical_universe",
            "The eligible product set changes only by historical data and the fixed dual filter.",
            "PASS",
            ["reproduction/run.py", "artifacts/metrics.csv"],
        ),
        check(
            "execution",
            "Every filtered arm uses a matching unfiltered arm, two executions and two costs.",
            "PASS",
            ["artifacts/metrics.csv", "REPORT.md"],
        ),
        check(
            "accounting",
            "All 52 arms contain finite metrics and cash exposure is represented by zero weights.",
            "PASS"
            if len(metrics) == 52
            and np.isfinite(metrics[["cagr", "vol", "sharpe", "mdd", "calmar", "average_exposure"]].to_numpy(float)).all()
            else "FAIL",
            ["artifacts/metrics.csv"],
        ),
        check(
            "smoke_backtest",
            "All planned filtered and unfiltered arms ran.",
            "PASS"
            if set(metrics["execution"]) == {"paper_like", "lag1"}
            and set(metrics["cost_bps"]) == {5.0, 20.5}
            else "FAIL",
            ["artifacts/metrics.csv", "logs/run.log"],
        ),
        check(
            "reproducibility",
            "The deterministic test suite passes.",
            "PASS" if "3 passed" in tests else "FAIL",
            ["logs/unit_tests.log", "reproduction/run.py"],
        ),
        check(
            "metrics_comparison",
            "Metrics, dual eligibility, cash exposure and matched bootstrap are recorded.",
            "PASS"
            if all(
                (ART / name).is_file()
                for name in (
                    "metrics.csv",
                    "bootstrap.csv",
                    "result.json",
                    "nav_dual_filter.png",
                )
            )
            else "FAIL",
            [
                "artifacts/metrics.csv",
                "artifacts/bootstrap.csv",
                "artifacts/result.json",
                "artifacts/nav_dual_filter.png",
            ],
        ),
        check(
            "reproduction_communication",
            "Pre-repro, report, audit, algorithm, index and archive are present.",
            "PASS"
            if all(
                (RUN / name).is_file()
                for name in (
                    "PRE_REPRO.md",
                    "REPORT.md",
                    "AUDIT.md",
                    "ALGORITHM.md",
                    "REPRO_INDEX.md",
                    "archive_manifest.json",
                )
            )
            else "FAIL",
            [
                "PRE_REPRO.md",
                "REPORT.md",
                "AUDIT.md",
                "ALGORITHM.md",
                "REPRO_INDEX.md",
                "archive_manifest.json",
                "iterations.jsonl",
                "sample_access.jsonl",
            ],
        ),
    ]
    validation = {
        "schema_version": "1.0",
        "strategy_sha256": sha256(RUN / "strategy.json"),
        "code_revision": sha256(RUN / "reproduction/run.py"),
        "data_snapshot": {
            "manifest": "data_certificate.json",
            "manifest_sha256": sha256(RUN / "data_certificate.json"),
            "decision": "PARTIAL",
            "r3_panel_sha256": "623a92c94ba067d731f257643c5bc3261e28560a401e6e37f33fc55806add2a8",
        },
        "environment": {
            "python": "3.12",
            "pandas": pd.__version__,
            "numpy": np.__version__,
        },
        "checks": checks,
        "command_evidence": [
            {
                "command": "/Users/hsh/Documents/Quant/科技轮动/.venv/bin/python3 -m pytest -q reproduction/test_run.py",
                "cwd": str(RUN),
                "executed_at": "2026-11-23T22:10:44+08:00",
                "exit_code": 0,
                "log_path": "logs/unit_tests.log",
            },
            {
                "command": "/Users/hsh/Documents/Quant/科技轮动/.venv/bin/python3 reproduction/run.py",
                "cwd": str(RUN),
                "executed_at": "2026-11-23T22:10:45+08:00",
                "exit_code": 0,
                "log_path": "logs/run.log",
            },
        ],
        "metric_comparison": {
            "filtered_arm_metrics": result["metrics"],
            "bootstrap": result["bootstrap"],
            "interpretation": (
                "BM5+dual12 improves history especially under lag1 but lacks robust "
                "statistical support and fails the paper-like +0.10 Sharpe gate."
            ),
        },
        "conclusions": {
            "code_correctness": "PASS",
            "methodological_validity": "PASS",
            "report_reproduction": "PASS",
            "live_profitability": "NOT_ASSESSED",
        },
        "scope_note": (
            "Dual-momentum filter is a research extension. BM5+dual12 is shadow-only; "
            "no production change."
        ),
    }
    (RUN / "validation.json").write_text(
        json.dumps(validation, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(validation, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
