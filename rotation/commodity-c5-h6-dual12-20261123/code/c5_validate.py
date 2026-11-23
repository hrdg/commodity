"""Engineering and causal checks for the 2015 commodity-proxy extension."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

RUN = Path(__file__).resolve().parent
ART = RUN / "artifacts"
_spec = importlib.util.spec_from_file_location("proxy2015_run", RUN / "run.py")
R = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(R)


def main() -> int:
    opens, closes, proxies, splices = R.build_asset_panel()
    checks = {}

    checks["coverage"] = {
        "status": "PASS",
        "criterion": "All six synthetic nodes are finite from 2015-01-05, with warm-up before start.",
        "first": str(closes.index.min().date()),
        "last": str(closes.index.max().date()),
        "strategy_start": str(R.START.date()),
        "rows": int(len(closes)),
        "all_finite": bool(
            np.isfinite(opens.to_numpy(float)).all()
            and np.isfinite(closes.to_numpy(float)).all()
        ),
        "minimum_price": float(min(opens.min().min(), closes.min().min())),
    }
    assert checks["coverage"]["first"] <= "2014-01-03"
    assert checks["coverage"]["last"] == "2026-11-06"
    assert checks["coverage"]["all_finite"]
    assert checks["coverage"]["minimum_price"] > 0

    splice_rows = []
    for row in splices.itertuples(index=False):
        switch = pd.Timestamp(row.actual_start)
        prior = closes.index[closes.index < switch][-1]
        continuity_error = abs(float(opens.at[switch, row.fund]) - float(closes.at[prior, row.fund]))
        splice_rows.append(
            {
                "fund": row.fund,
                "switch": row.actual_start,
                "continuity_error": continuity_error,
            }
        )
    max_continuity = max(row["continuity_error"] for row in splice_rows)
    checks["splice_continuity"] = {
        "status": "PASS" if max_continuity < 1e-10 else "FAIL",
        "criterion": "Actual ETF first open equals the previous proxy close after scaling.",
        "switches": splice_rows,
        "max_error": max_continuity,
    }
    assert max_continuity < 1e-10
    assert len(splice_rows) == 5

    cost = 5 / 10000.0
    sim = R.simulate_monthly(closes, opens, cost, rank_k=2, splices=splices)
    ret, exposure = R.apply_tip_dd(sim["ret"], cost, tip_name="S", dd=True)
    expected = sim["gross"] - cost * sim["turnover"] - sim["splice_fee"]
    accounting_error = float((sim["ret"] - expected).abs().max())
    valid_holds = sim["hold"].dropna().isin(R.FUNDS)
    checks["ledger"] = {
        "status": "PASS"
        if accounting_error < 1e-12
        and bool(valid_holds.all())
        and bool(exposure.between(0.0, 1.0).all())
        else "FAIL",
        "criterion": "C5 net return reconciles to gross, turnover and splice fees; holdings and overlays are bounded.",
        "accounting_max_error": accounting_error,
        "invalid_holdings": int((~valid_holds).sum()),
        "exposure_min": float(exposure.min()),
        "exposure_max": float(exposure.max()),
        "days": int(len(sim)),
    }
    assert checks["ledger"]["status"] == "PASS"

    # Prefix invariance: changing prices after a cutoff cannot change prior weights/holds.
    cutoff = pd.Timestamp("2022-12-30")
    perturbed_open = opens.copy()
    perturbed_close = closes.copy()
    perturbed_open.loc[perturbed_open.index > cutoff] *= 1.37
    perturbed_close.loc[perturbed_close.index > cutoff] *= 0.71
    perturbed = R.simulate_monthly(
        perturbed_close,
        perturbed_open,
        cost,
        rank_k=2,
        splices=splices,
    )
    compare_end = closes.index[closes.index <= cutoff][-2]
    hold_error = int(
        (
            sim.loc[:compare_end, "hold"].fillna("NONE").astype(str)
            != perturbed.loc[:compare_end, "hold"].fillna("NONE").astype(str)
        ).sum()
    )
    ret_error = float(
        (sim.loc[:compare_end, "ret"] - perturbed.loc[:compare_end, "ret"]).abs().max()
    )
    checks["future_perturbation"] = {
        "status": "PASS" if hold_error == 0 and ret_error < 1e-12 else "FAIL",
        "criterion": "Perturbing all prices after cutoff leaves prior holdings and returns unchanged.",
        "cutoff": str(cutoff.date()),
        "compare_end": str(compare_end.date()),
        "holding_difference_count": hold_error,
        "return_max_error": ret_error,
    }
    assert checks["future_perturbation"]["status"] == "PASS"

    overlap = pd.read_csv(ART / "parent_overlap.csv").iloc[0]
    checks["parent_overlap"] = {
        "status": "PASS" if float(overlap["return_correlation"]) > 0.95 else "PARTIAL",
        "criterion": "Post-2022 extended panel reproduces the frozen actual-ETF parent path.",
        "correlation": float(overlap["return_correlation"]),
        "mean_abs_daily_difference": float(overlap["mean_abs_daily_difference"]),
        "annualized_return_difference": float(overlap["annualized_return_difference"]),
    }
    assert checks["parent_overlap"]["status"] == "PASS"

    reconciliation = pd.read_csv(ART / "reconciliation.csv")
    checks["proxy_reconciliation"] = {
        "status": "PARTIAL",
        "criterion": "Proxy return correlation and tracking difference must be disclosed on post-listing overlap.",
        "funds": reconciliation.to_dict(orient="records"),
        "minimum_correlation": float(reconciliation["return_correlation"].min()),
        "maximum_abs_annualized_difference": float(
            reconciliation["annualized_return_difference"].abs().max()
        ),
    }

    metrics = pd.read_csv(ART / "metrics.csv")
    primary5 = metrics[
        metrics["arm"].eq("RANK2_TIPS_DD") & metrics["cost_bps"].eq(5.0)
    ].iloc[0]
    primary20 = metrics[
        metrics["arm"].eq("RANK2_TIPS_DD") & metrics["cost_bps"].eq(20.5)
    ].iloc[0]
    checks["cost_survival"] = {
        "status": "PASS"
        if float(primary5["cagr"]) > 0
        and float(primary20["cagr"]) > 0
        and float(primary20["sharpe"]) > 1.0
        else "PARTIAL",
        "criterion": "Primary arm remains economically positive after 20.5bp one-way cost.",
        "five_bp": {
            "cagr": float(primary5["cagr"]),
            "sharpe": float(primary5["sharpe"]),
            "mdd": float(primary5["mdd"]),
        },
        "twenty_point_five_bp": {
            "cagr": float(primary20["cagr"]),
            "sharpe": float(primary20["sharpe"]),
            "mdd": float(primary20["mdd"]),
        },
    }

    timing = pd.read_csv(ART / "dd_timing_metrics.csv")
    s_timing = timing[
        timing["tip"].eq("S") & timing["cost_bps"].eq(5.0)
    ].set_index("implementation")
    same = s_timing.loc["same_day"]
    next_session = s_timing.loc["next_session"]
    timing_difference = {
        "cagr": float(same["cagr"] - next_session["cagr"]),
        "sharpe": float(same["sharpe"] - next_session["sharpe"]),
        "mdd": float(same["mdd"] - next_session["mdd"]),
    }
    checks["dd_time_alignment"] = {
        "status": "FAIL"
        if abs(timing_difference["sharpe"]) > 1e-6
        or abs(timing_difference["cagr"]) > 1e-6
        else "PASS",
        "criterion": "A close-based DD state must affect a later executable return, not the return that created it.",
        "same_day": same.to_dict(),
        "next_session": next_session.to_dict(),
        "same_minus_next_session": timing_difference,
        "evidence": "artifacts/dd_timing_metrics.csv and EVENT_AUDIT_2025Q4_2026Q1.md",
    }

    status = (
        "PASS_WITH_LIMITATIONS"
        if all(
            item["status"] in ("PASS", "PARTIAL")
            for item in checks.values()
        )
        else (
            "FAIL_DD_SAME_DAY_LOOKAHEAD"
            if checks["dd_time_alignment"]["status"] == "FAIL"
            else "FAIL"
        )
    )
    output = {
        "status": status,
        "generated_at": "2026-11-09T00:00:00+08:00",
        "checks": checks,
        "limitations": [
            "The pre-listing series are proxies, not actual six-ETF history.",
            "USO has a low daily-return correlation with 160723 because of timezone, tracking and LOF-price noise.",
            "Main-continuous futures roll treatment is not certified.",
            "M0 roll adjustment lacks complete contract-level lineage.",
            "The earlier period is retrospective after the 2022+ model was observed; it is not pristine OOS.",
            "Proxy data are research-only and do not support a production promotion.",
            "The same-day DD path is invalid for executable performance; use the next-session rebuild.",
        ],
    }
    (RUN / "validation.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if not status.startswith("FAIL") else 1


if __name__ == "__main__":
    raise SystemExit(main())
