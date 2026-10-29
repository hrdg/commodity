import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import strategy  # noqa: E402


class TestPremiumStrategy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = json.loads((ROOT / "config.json").read_text())
        cls.out, cls.report = strategy.run(cls.cfg)

    def test_performance_matches_frozen_result(self):
        st = self.report["strategy"]
        self.assertGreater(st["cagr"], 0.22)
        self.assertGreater(st["sharpe"], 1.00)
        self.assertGreater(st["mdd"], -0.25)
        self.assertLess(self.report["buy_hold"]["cagr"], 0.12)

    def test_positions_are_long_only(self):
        p = self.out["held_position"]
        self.assertTrue(p.between(0, 1).all())
        self.assertGreater(p.mean(), 0.5)

    def test_premium_weights(self):
        d = self.out.dropna(subset=["premium"])
        high = d[d.premium > 0.10]
        mid = d[(d.premium > 0.05) & (d.premium <= 0.10)]
        low = d[d.premium <= 0.05]
        self.assertTrue((high.premium_weight == 0).all())
        self.assertTrue(mid.premium_weight.isin([0, 1]).all())
        self.assertTrue((low.premium_weight == 1).all())


if __name__ == "__main__":
    unittest.main()
