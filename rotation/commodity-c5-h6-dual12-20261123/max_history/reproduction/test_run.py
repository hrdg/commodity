from __future__ import annotations

import pandas as pd

import run


def test_partial_node_does_not_fill_missing_group() -> None:
    product = pd.DataFrame(
        {
            "date": pd.to_datetime(["2020-01-31"] * 4),
            "product": ["CU", "AL", "ZN", "AU"],
            "bm5": [0.01, 0.02, 0.0, 0.03],
        }
    )
    output = run.node_panel_partial(product)
    assert pd.notna(output.loc["2020-01-31", "159980.XSHE"])
    assert pd.notna(output.loc["2020-01-31", "518880.XSHG"])
    assert pd.isna(output.loc["2020-01-31", "159985.XSHE"])
    assert pd.isna(output.loc["2020-01-31", "159981.XSHE"])


def test_partial_metadata_has_no_synthetic_prices() -> None:
    assert run.NODE_GROUPS["159980.XSHE"] == ("CU", "AL", "ZN")
    assert run.NODE_GROUPS["159981.XSHE"] == ("TA", "MA", "FG")
