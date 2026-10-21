import pathlib, sys, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import strategy

class TestStrategy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pos, cls.parts = strategy.build()

    def test_positions_discrete(self):
        self.assertTrue(set(self.pos.unique()).issubset({-1.0, 0.0, 1.0}))

    def test_data_present(self):
        for f in ['CU0_main.csv','eastmoney_usd_index_udi.csv','cboe_VIX_History.csv','ism_manufacturing_pmi_eastmoney.csv','cftc_copper_net.csv']:
            self.assertTrue((strategy.DATA/f).exists())

    def test_holdout(self):
        m = strategy.metrics(self.pos.loc['2025-01-01':'2026-10-20'], self.parts['cu'].loc['2025-01-01':'2026-10-20'])
        self.assertGreater(m['sharpe'], 0.8)
        self.assertGreater(m['calmar'], 0.8)

if __name__ == '__main__':
    unittest.main()
