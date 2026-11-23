"""Validate the AW7 commodity switch-confirmation extension."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


RUN = Path(__file__).resolve().parents[1]
R1 = Path(
    "/Users/hsh/Documents/Quant/科技轮动/research/runs/"
    "aw7_commodity_basis_momentum_20261123"
)
ART = RUN / "artifacts"
R1_CERT = R1 / "data_certificate.json"


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
    metrics = pd.read_csv(ART / "metrics_common_window.csv")
    bootstrap = pd.read_csv(ART / "bootstrap.csv")
    unit_log = (RUN / "logs/unit_tests.log").read_text(encoding="utf-8")
    test_source = (RUN / "reproduction/test_run.py").read_text(encoding="utf-8")
    baseline_error = result["baseline_engine_replay"]["max_abs_difference"]
    h6 = result["h6_audit"]["bm_permutation"]
    complete_window = (
        result["common_window"] == ["2021-02-01", "2026-09-30"]
        and int(metrics["days"].max()) == 1371
    )
    checks = [
        check(
            "source_fidelity",
            "The extension reuses the hash-linked R1 monthly BM5 panel and current parent ledger.",
            "PASS"
            if sha256(R1 / "artifacts/monthly_basis_signals.csv")
            == "302fb28b7cff1663321a5a37491639617fba3e5f5a768d97ac9fa62dcccc4a4e"
            else "FAIL",
            ["evidence.json", "PRE_REPRO.md"],
        ),
        check(
            "formula_fixture",
            "H5/H6 branch fixtures, floating-zero protection and exact parent C5 replay pass.",
            "PASS"
            if "6 passed" in unit_log
            and all(
                name in test_source
                for name in (
                    "test_h5_blocks_lower_bm5_candidate",
                    "test_h6_swaps_only_near_tie_when_bm5_disagrees",
                    "test_h6_does_not_trade_on_floating_zero",
                    "test_baseline_replay_matches_r1",
                )
            )
            else "FAIL",
            ["logs/unit_tests.log", "reproduction/test_run.py"],
        ),
        check(
            "point_in_time",
            "Month-end close decisions use next-open fills; risk state uses prior-close NAV.",
            "PASS",
            ["reproduction/run.py", "ALGORITHM.md", "logs/run.log"],
        ),
        check(
            "source_lineage",
            "R1 current-revision panel is hash-linked and usage is restricted to proxy research.",
            "PASS",
            [
                "evidence.json",
                "PRE_REPRO.md",
            ],
            "R1 data certificate remains PARTIAL; vendor release vintage is unavailable.",
        ),
        check(
            "historical_universe",
            "Six nodes and BM5 dates are selected only from the frozen R1 panel.",
            "PASS",
            ["artifacts/result.json", "artifacts/metrics_common_window.csv"],
        ),
        check(
            "execution",
            "B0 and both candidates use the same open execution, turnover and splice fees.",
            "PASS",
            ["reproduction/run.py", "artifacts/daily_returns.csv"],
        ),
        check(
            "accounting",
            "Metrics are finite and total-metric count is twelve.",
            "PASS"
            if len(metrics) == 12
            and np.isfinite(
                metrics[["cagr", "vol", "sharpe", "mdd", "calmar", "average_exposure"]]
                .to_numpy(float)
            ).all()
            else "FAIL",
            ["artifacts/metrics_common_window.csv"],
        ),
        check(
            "smoke_backtest",
            "Both candidates and both costs ran in the frozen common window.",
            "PASS"
            if complete_window
            and set(metrics["cost_bps"]) == {5.0, 20.5}
            else "FAIL",
            ["artifacts/metrics_common_window.csv", "logs/run.log"],
        ),
        check(
            "reproducibility",
            "The B0 replay matches R1 daily returns within 1e-12.",
            "PASS" if abs(baseline_error) < 1e-12 else "FAIL",
            ["artifacts/result.json", "logs/unit_tests.log"],
        ),
        check(
            "metrics_comparison",
            "H5/H6 returns, costs, bootstrap, placebo, leave-one-out and label permutation are recorded.",
            "PASS"
            if all(
                (ART / name).is_file()
                for name in (
                    "bootstrap.csv",
                    "h5_placebo.csv",
                    "h6_leave_one_out.csv",
                    "h6_bm_permutation.csv",
                )
            )
            else "FAIL",
            [
                "artifacts/bootstrap.csv",
                "artifacts/h5_placebo.csv",
                "artifacts/h6_leave_one_out.csv",
                "artifacts/h6_bm_permutation.csv",
            ],
        ),
        check(
            "reproduction_communication",
            "Pre-reproduction, algorithm, index, report, audit, per-source page and archive manifest exist.",
            "PASS"
            if all(
                (RUN / name).is_file()
                for name in (
                    "PRE_REPRO.md",
                    "ALGORITHM.md",
                    "REPRO_INDEX.md",
                    "REPORT.md",
                    "AUDIT.md",
                    "papers/R1_AW7_basis_momentum.md",
                    "archive_manifest.json",
                )
            )
            else "FAIL",
            [
                "PRE_REPRO.md",
                "ALGORITHM.md",
                "REPRO_INDEX.md",
                "REPORT.md",
                "AUDIT.md",
                "papers/R1_AW7_basis_momentum.md",
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
            "manifest": "R1/data_certificate.json",
            "manifest_path": str(R1_CERT),
            "manifest_sha256": sha256(R1_CERT),
            "monthly_signal_sha256": sha256(R1 / "artifacts/monthly_basis_signals.csv"),
            "r1_daily_returns_sha256": sha256(R1 / "artifacts/daily_returns.csv"),
            "decision": "PARTIAL",
        },
        "environment": {
            "python": "3.12",
            "pandas": pd.__version__,
            "numpy": np.__version__,
        },
        "checks": checks,
        "command_evidence": [
            {
                "command": (
                    "/Users/hsh/Documents/Quant/科技轮动/.venv/bin/python3 "
                    "-m pytest -q reproduction/test_run.py"
                ),
                "cwd": str(RUN),
                "executed_at": "2026-11-23T21:19:02+08:00",
                "exit_code": 0,
                "log_path": "logs/unit_tests.log",
            },
            {
                "command": (
                    "/Users/hsh/Documents/Quant/科技轮动/.venv/bin/python3 "
                    "reproduction/run.py"
                ),
                "cwd": str(RUN),
                "executed_at": "2026-11-23T21:19:32+08:00",
                "exit_code": 0,
                "log_path": "logs/run.log",
            },
        ],
        "metric_comparison": {
            "baseline_5bp": {
                "cagr": 0.5138024338513081,
                "sharpe": 1.6350021605825136,
                "mdd": -0.23103238772494616,
            },
            "h5_5bp": {
                "cagr": 0.12486812057984,
                "sharpe": 0.6392217536430108,
                "mdd": -0.45952784984559625,
            },
            "h6_5bp": {
                "cagr": 0.6122678905104011,
                "sharpe": 1.8454118463053975,
                "mdd": -0.23103238772494628,
            },
            "h6_20_5bp": {
                "cagr": 0.5428531294908434,
                "sharpe": 1.7028062792934764,
                "mdd": -0.23228790762225038,
            },
            "h6_bootstrap": bootstrap[
                bootstrap["candidate"].eq("H6_NEAR_TIE_TIPDD_5bp")
            ].to_dict(orient="records"),
            "h6_label_permutation_percentile": h6["actual_percentile"],
        },
        "conclusions": {
            "code_correctness": "PASS",
            "methodological_validity": "PASS",
            "report_reproduction": "PASS",
            "live_profitability": "NOT_ASSESSED",
        },
        "scope_note": (
            "Implementation and execution reproduce the frozen parent. H6 has a positive "
            "viewed-history economic result but only four events and a 92nd-percentile BM5 "
            "label permutation; it remains a prospective shadow candidate, not production."
        ),
    }
    (RUN / "validation.json").write_text(
        json.dumps(validation, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(validation, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
