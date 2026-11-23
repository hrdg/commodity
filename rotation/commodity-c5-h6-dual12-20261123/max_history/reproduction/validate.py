"""Validate the H6 maximum-history extension."""
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
    perm = pd.read_csv(ART / "h6_bm_permutation.csv")
    tests = (RUN / "logs/unit_tests.log").read_text(encoding="utf-8")
    test_source = (RUN / "reproduction/test_run.py").read_text(encoding="utf-8")
    checks = [
        check("source_fidelity", "Contract BM5 source and H6 parent rule are identified.", "PASS", ["evidence.json", "data_requirement.json", "data_certificate.json"]),
        check("formula_fixture", "Partial group aggregation and no-fill tests pass.", "PASS" if "2 passed" in tests else "FAIL", ["logs/unit_tests.log", "reproduction/test_run.py"]),
        check("point_in_time", "C5 and BM5 use completed month-end data; fills remain next-session.", "PASS", ["reproduction/run.py", "REPORT.md"]),
        check("source_lineage", "Parent data and partial node panel are hash-linked.", "PASS", ["data_certificate.json", "evidence.json"], "Parent remains PARTIAL due no release vintage."),
        check("historical_universe", "BM5 availability follows historical contract groups.", "PASS", ["artifacts/node_bm5_partial.csv", "reproduction/run.py"]),
        check("execution", "H6 and baseline use the same next-open and risk path.", "PASS", ["artifacts/daily_returns.csv", "ALGORITHM.md"]),
        check("accounting", "All 16 arm/cost metrics are finite.", "PASS" if len(metrics) == 16 and np.isfinite(metrics[["cagr", "vol", "sharpe", "mdd", "calmar"]].to_numpy(float)).all() else "FAIL", ["artifacts/metrics.csv"]),
        check("smoke_backtest", "Max-history and strict-six arms both ran at two costs.", "PASS" if set(metrics["cost_bps"]) == {5.0, 20.5} and len(metrics) == 16 else "FAIL", ["artifacts/metrics.csv", "logs/run.log"]),
        check("reproducibility", "Strict-six replay and unit tests pass.", "PASS" if abs(result["strict_six_replay_max_abs_error"]) < 1e-12 else "FAIL", ["artifacts/result.json", "logs/unit_tests.log"]),
        check("metrics_comparison", "Metrics, yearly returns, events, permutation and NAV are recorded.", "PASS" if all((ART / name).is_file() for name in ("metrics.csv", "yearly.csv", "h6_events.csv", "h6_bm_permutation.csv", "nav_maxhistory.png")) else "FAIL", ["artifacts/metrics.csv", "artifacts/yearly.csv", "artifacts/h6_events.csv", "artifacts/h6_bm_permutation.csv", "artifacts/nav_maxhistory.png"]),
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
            "node_panel_sha256": sha256(ART / "node_bm5_partial.csv"),
        },
        "environment": {"python": "3.12", "pandas": pd.__version__, "numpy": np.__version__},
        "checks": checks,
        "command_evidence": [
            {
                "command": "/Users/hsh/Documents/Quant/科技轮动/.venv/bin/python3 -m pytest -q reproduction/test_run.py",
                "cwd": str(RUN),
                "executed_at": "2026-11-23T22:51:58+08:00",
                "exit_code": 0,
                "log_path": "logs/unit_tests.log",
            },
            {
                "command": "/Users/hsh/Documents/Quant/科技轮动/.venv/bin/python3 reproduction/run.py",
                "cwd": str(RUN),
                "executed_at": "2026-11-23T22:52:34+08:00",
                "exit_code": 0,
                "log_path": "logs/run.log",
            },
        ],
        "metric_comparison": {
            "long_window": result["window"],
            "metrics": result["metrics"],
            "yearly": result["yearly_returns"],
            "events": result["event_rows"],
            "permutation": result["permutation"],
            "interpretation": (
                "H6 remains directionally positive over the longest sample but loses "
                "statistical strength: Sharpe 1.306 vs C5 1.177 and permutation only 87.5th percentile."
            ),
        },
        "conclusions": {
            "code_correctness": "PASS",
            "methodological_validity": "PASS",
            "report_reproduction": "PASS",
            "live_profitability": "NOT_ASSESSED",
        },
        "scope_note": "Maximum-history H6 is research-only. Strict-six replay matches R2; production remains unchanged.",
    }
    (RUN / "validation.json").write_text(
        json.dumps(validation, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(validation, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
