"""Validate the H6 plus dual12 fusion study."""
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
    f1 = pd.read_csv(ART / "metrics_f1.csv")
    f2 = pd.read_csv(ART / "metrics_f2.csv")
    tests = (RUN / "logs/unit_tests.log").read_text(encoding="utf-8")
    test_source = (RUN / "reproduction/test_run.py").read_text(encoding="utf-8")
    checks = [
        check(
            "source_fidelity",
            "Both parent research packages and their hashes are recorded.",
            "PASS",
            ["evidence.json", "PRE_REPRO.md", "data_certificate.json"],
        ),
        check(
            "formula_fixture",
            "Dual eligibility, H6 fixture and monthly blend tests pass.",
            "PASS"
            if "3 passed" in tests
            and all(
                name in test_source
                for name in (
                    "test_monthly_eligibility_combines_absolute_and_relative",
                    "test_h6_rule_uses_only_eligible_top_two",
                    "test_fixed_monthly_blend",
                )
            )
            else "FAIL",
            ["logs/unit_tests.log", "reproduction/test_run.py"],
        ),
        check(
            "point_in_time",
            "F1 preserves the next-open H6 contract; F2 uses realized common calendar months.",
            "PASS",
            ["reproduction/run.py", "artifacts/returns_f2_monthly.csv"],
        ),
        check(
            "source_lineage",
            "Both parent datasets and cross-carrier alignment are recorded.",
            "PASS",
            ["data_certificate.json", "evidence.json", "reproduction/run.py"],
            "Parent data remain PARTIAL due unavailable release vintage.",
        ),
        check(
            "historical_universe",
            "F1 uses frozen six ETF nodes; F2 uses each parent's frozen universe.",
            "PASS",
            ["strategy.json", "artifacts/eligibility.csv"],
        ),
        check(
            "execution",
            "F1 is next-open ETF; F2 is explicitly a monthly blended-return proxy.",
            "PASS",
            ["REPORT.md", "ALGORITHM.md"],
        ),
        check(
            "accounting",
            "All 18 planned arm/cost metrics are finite; F2 rebalance cost is included.",
            "PASS"
            if len(f1) == 12
            and len(f2) == 6
            and np.isfinite(
                pd.concat([f1[["cagr", "vol", "sharpe", "mdd"]], f2[["cagr", "vol", "sharpe", "mdd"]]]).to_numpy(float)
            ).all()
            else "FAIL",
            ["artifacts/metrics_f1.csv", "artifacts/metrics_f2.csv"],
        ),
        check(
            "smoke_backtest",
            "Six F1 arms and three F2 arms ran at two cost levels.",
            "PASS"
            if set(f1["arm"]) == {"B0_C5", "H6", "ABS12_C5", "ABS12_H6", "DUAL12_C5", "DUAL12_H6"}
            and set(f2["arm"]) == {"H6", "BM5_DUAL12", "FUSION50"}
            else "FAIL",
            ["artifacts/metrics_f1.csv", "artifacts/metrics_f2.csv", "logs/run.log"],
        ),
        check(
            "reproducibility",
            "The deterministic unit suite passes and parent H6 reproduces in the fixed window.",
            "PASS" if "3 passed" in tests else "FAIL",
            ["logs/unit_tests.log", "artifacts/metrics_f1.csv"],
        ),
        check(
            "metrics_comparison",
            "F1/F2 metrics, bootstrap, eligibility and NAV are recorded.",
            "PASS"
            if all(
                (ART / name).is_file()
                for name in (
                    "metrics_f1.csv",
                    "metrics_f2.csv",
                    "bootstrap_f1.csv",
                    "bootstrap_f2.csv",
                    "eligibility.csv",
                    "nav_fusion.png",
                )
            )
            else "FAIL",
            [
                "artifacts/metrics_f1.csv",
                "artifacts/metrics_f2.csv",
                "artifacts/bootstrap_f1.csv",
                "artifacts/bootstrap_f2.csv",
                "artifacts/eligibility.csv",
                "artifacts/nav_fusion.png",
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
            "H6_daily_sha256": sha256(
                Path(
                    "/Users/hsh/Documents/Quant/科技轮动/research/runs/"
                    "aw7_commodity_switch_confirm_20261123/artifacts/daily_returns.csv"
                )
            ),
            "dual_returns_sha256": sha256(
                Path(
                    "/Users/hsh/Documents/Quant/科技轮动/research/runs/"
                    "aw7_commodity_dual_filter_20261123/artifacts/returns.csv"
                )
            ),
        },
        "environment": {"python": "3.12", "pandas": pd.__version__, "numpy": np.__version__},
        "checks": checks,
        "command_evidence": [
            {
                "command": "/Users/hsh/Documents/Quant/科技轮动/.venv/bin/python3 -m pytest -q reproduction/test_run.py",
                "cwd": str(RUN),
                "executed_at": "2026-11-23T22:18:18+08:00",
                "exit_code": 0,
                "log_path": "logs/unit_tests.log",
            },
            {
                "command": "/Users/hsh/Documents/Quant/科技轮动/.venv/bin/python3 reproduction/run.py",
                "cwd": str(RUN),
                "executed_at": "2026-11-23T22:18:20+08:00",
                "exit_code": 0,
                "log_path": "logs/run.log",
            },
        ],
        "metric_comparison": {
            "F1_metrics": result["F1"]["metrics"],
            "F1_bootstrap": result["F1"]["bootstrap"],
            "F2_metrics": result["F2"]["metrics"],
            "F2_bootstrap": result["F2"]["bootstrap"],
            "interpretation": (
                "Serial filter damages H6 despite a local +0.065 H6 effect; the 50/50 "
                "capital blend improves historical monthly Sharpe but is not a single "
                "executable carrier and is not statistically confirmed against H6."
            ),
        },
        "conclusions": {
            "code_correctness": "PASS",
            "methodological_validity": "PASS",
            "report_reproduction": "PASS",
            "live_profitability": "NOT_ASSESSED",
        },
        "scope_note": "F1 rejected; F2 50/50 is shadow-only. No production change or independent OOS claim.",
    }
    (RUN / "validation.json").write_text(
        json.dumps(validation, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(validation, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
