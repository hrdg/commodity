import pathlib, sys, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import strategy

class TestStrategy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pos, cls.parts = strategy.build()

    def test_positions_are_discrete(self):
        self.assertTrue(set(self.pos.unique()).issubset({-1.0, 0.0, 1.0}))

    def test_data_present(self):
        for f in ['M0_main_sina.csv','M0_main_2025_2026.csv','m_basis_2016_2024.csv','m_warehouse_receipt_latest.csv']:
            self.assertTrue((strategy.DATA/f).exists())

    def test_holdout_sharpe(self):
        m = strategy.metrics(self.pos.loc['2025-01-01':'2026-10-20'], self.parts['M'].loc['2025-01-01':'2026-10-20'])
        self.assertGreater(m['sharpe'], 0.8)
        self.assertGreater(m['calmar'], 0.6)

if __name__ == '__main__':
    unittest.main()
