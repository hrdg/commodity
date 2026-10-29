import json
import pathlib
import sys
import unittest

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import lab
import strategy


class TestAsphaltDualCheap(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = json.loads((ROOT / "config.json").read_text())
        cls.bx, cls.crack_z, cls.spread_z, cls.signal, cls.pnl, cls.pos = strategy.build(cls.cfg)

    def test_long_only_discrete_positions(self):
        self.assertTrue(set(self.pos.unique()).issubset({0.0, 1.0}))
        self.assertAlmostEqual(float(self.pos.max()), 1.0)
        self.assertGreaterEqual(float(self.pos.min()), 0.0)

    def test_signal_requires_both_legs_cheap(self):
        expected = ((self.crack_z < 0) & (self.spread_z < 0)).astype(float)
        expected = expected.where(self.crack_z.notna() & self.spread_z.notna(), 0.0)
        pd.testing.assert_series_equal(self.signal, expected, check_names=False)

    def test_holdout_performance_gate(self):
        pnl = self.pnl.loc["2022-01-01":self.cfg["end"]]
        pos = self.pos.reindex(pnl.index)
        m = lab.metrics(pnl, pos)
        self.assertGreater(m["cagr"], 0.11)
        self.assertGreater(m["sharpe"], 0.85)
        self.assertGreater(m["calmar"], 0.90)
        self.assertGreater(m["mdd"], -0.15)

    def test_data_checksums(self):
        import hashlib

        for path in sorted((ROOT / "data").glob("*.csv")):
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            listed = [
                line.split()[0]
                for line in (ROOT / "data" / "SHA256SUMS").read_text().splitlines()
                if line.strip().endswith(path.name)
            ]
            self.assertEqual(listed, [digest], path.name)


if __name__ == "__main__":
    unittest.main()
