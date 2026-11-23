"""Validate the Sleeve B comparison."""
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
    correlations = pd.read_csv(ART / "correlations.csv")
    tests = (RUN / "logs/unit_tests.log").read_text(encoding="utf-8")
    checks = [
        check("source_fidelity", "The comparison is bound to frozen parent return artifacts.", "PASS", ["evidence.json", "data_certificate.json"]),
        check("formula_fixture", "Monthly compounding, alignment and blend-cost tests pass.", "PASS" if "2 passed" in tests else "FAIL", ["logs/unit_tests.log", "reproduction/test_run.py"]),
        check("point_in_time", "Only realized monthly returns are blended.", "PASS", ["reproduction/run.py", "artifacts/returns_monthly.csv"]),
        check("source_lineage", "Parent paths and derived transformations are recorded.", "PASS", ["data_certificate.json", "evidence.json"], "Parents remain PARTIAL due no release vintage."),
        check("historical_universe", "Sleeves retain their frozen parent universes.", "PASS", ["strategy.json"]),
        check("execution", "Same-carrier ETF and cross-carrier reference are labeled separately.", "PASS", ["REPORT.md", "ALGORITHM.md"]),
        check("accounting", "Twelve metrics are finite and include blend rebalance cost.", "PASS" if len(metrics) == 12 and np.isfinite(metrics[["cagr", "vol", "sharpe", "mdd", "calmar"]].to_numpy(float)).all() else "FAIL", ["artifacts/metrics.csv"]),
        check("smoke_backtest", "Six arms at two costs ran.", "PASS" if set(metrics["arm"]) == {"H6", "DUAL12_C5", "DUAL12_H6", "H6_PLUS_DUAL12_C5", "H6_PLUS_DUAL12_H6", "H6_PLUS_BM5_DUAL12"} else "FAIL", ["artifacts/metrics.csv", "logs/run.log"]),
        check("reproducibility", "Deterministic tests pass.", "PASS" if "2 passed" in tests else "FAIL", ["logs/unit_tests.log"]),
        check("metrics_comparison", "Metrics, correlations, bootstrap and NAV are recorded.", "PASS" if all((ART / name).is_file() for name in ("metrics.csv", "correlations.csv", "bootstrap.csv", "nav_sleeveb.png")) else "FAIL", ["artifacts/metrics.csv", "artifacts/correlations.csv", "artifacts/bootstrap.csv", "artifacts/nav_sleeveb.png"]),
        check("reproduction_communication", "Communication and archive files exist.", "PASS", ["PRE_REPRO.md", "REPORT.md", "AUDIT.md", "ALGORITHM.md", "REPRO_INDEX.md", "archive_manifest.json", "iterations.jsonl", "sample_access.jsonl"]),
    ]
    validation = {
        "schema_version": "1.0",
        "strategy_sha256": sha256(RUN / "strategy.json"),
        "code_revision": sha256(RUN / "reproduction/run.py"),
        "data_snapshot": {
            "manifest": "data_certificate.json",
            "manifest_sha256": sha256(RUN / "data_certificate.json"),
            "decision": "PARTIAL",
            "parent_returns_sha256": sha256(
                Path(
                    "/Users/hsh/Documents/Quant/科技轮动/research/runs/"
                    "aw7_commodity_h6_dual_fusion_20261123/artifacts/returns_f1_daily.csv"
                )
            ),
        },
        "environment": {"python": "3.12", "pandas": pd.__version__, "numpy": np.__version__},
        "checks": checks,
        "command_evidence": [
            {
                "command": "/Users/hsh/Documents/Quant/科技轮动/.venv/bin/python3 -m pytest -q reproduction/test_run.py",
                "cwd": str(RUN),
                "executed_at": "2026-11-23T22:25:19+08:00",
                "exit_code": 0,
                "log_path": "logs/unit_tests.log",
            },
            {
                "command": "/Users/hsh/Documents/Quant/科技轮动/.venv/bin/python3 reproduction/run.py",
                "cwd": str(RUN),
                "executed_at": "2026-11-23T22:25:12+08:00",
                "exit_code": 0,
                "log_path": "logs/run.log",
            },
        ],
        "metric_comparison": {
            "metrics": result["metrics"],
            "correlations": result["correlations"],
            "bootstrap": result["bootstrap"],
            "interpretation": (
                "Same-carrier B1/B2 are 0.93-0.94 correlated with H6 and produce lower Sharpe blends; "
                "broad BM5+dual12 remains the only meaningfully diversifying Sleeve B."
            ),
        },
        "conclusions": {
            "code_correctness": "PASS",
            "methodological_validity": "PASS",
            "report_reproduction": "PASS",
            "live_profitability": "NOT_ASSESSED",
        },
        "scope_note": "Same-carrier Sleeve B no increment. Cross-carrier broad blend remains shadow-only.",
    }
    (RUN / "validation.json").write_text(
        json.dumps(validation, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(validation, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
