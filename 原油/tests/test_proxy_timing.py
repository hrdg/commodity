import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import strategy  # noqa: E402


class TestUSOProxyTiming(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.px = strategy.load_price()
        cls.nav = strategy.load_nav()
        cls.uso = pd.read_csv(strategy.DATA / "uso.csv", parse_dates=["date"]).set_index("date")["close"].sort_index()
        cls.inputs = strategy.proxy_uso_inputs(cls.px, cls.nav, cls.uso, 3)

    def test_us_session_is_strictly_before_china_decision(self):
        d = self.inputs.dropna(subset=["us_end_date"])
        self.assertTrue((d.us_end_date < d.index.to_series()).all())

    def test_us_holiday_uses_last_completed_session(self):
        self.assertEqual(pd.Timestamp(self.inputs.loc["2024-07-05", "us_end_date"]),
                         pd.Timestamp("2024-07-03"))

    def test_china_holiday_keeps_us_gap(self):
        self.assertEqual(pd.Timestamp(self.inputs.loc["2024-10-08", "us_end_date"]),
                         pd.Timestamp("2024-10-07"))

    def test_nav_date_is_at_least_three_china_sessions_old(self):
        idx = self.px.index
        for i, date in enumerate(idx):
            if i < 3 or pd.isna(self.inputs.loc[date, "nav_date"]):
                continue
            self.assertLessEqual(pd.Timestamp(self.inputs.loc[date, "nav_date"]), idx[i - 3])

    def test_current_signal_dates(self):
        row = self.inputs.loc["2026-10-30"]
        self.assertEqual(pd.Timestamp(row["us_end_date"]), pd.Timestamp("2026-10-29"))
        self.assertEqual(pd.Timestamp(row["nav_date"]), pd.Timestamp("2026-10-27"))


if __name__ == "__main__":
    unittest.main()
