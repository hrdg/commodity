"""Read-only strategy audit; writes evidence only beside this script.

Sensitivity calculations are diagnostics, not replacement strategy results.
Run with the research environment's Python from any working directory.
"""
import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import strategy


def load(name, col):
    return pd.read_csv(ROOT / 'data' / f'{name}.csv', parse_dates=['date']).set_index('date')[col].sort_index()


def summarize(pnl, pos):
    return {k: strategy.metrics(pnl, pos)[k] for k in ['cagr', 'sharpe', 'calmar', 'mdd', 'final']}


def main():
    evidence = {
        'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'environment': {'python': platform.python_version(), 'pandas': pd.__version__, 'numpy': np.__version__},
        'hashes': {}, 'configs': {},
        'warning': 'Reproduction and diagnostic sensitivities do not certify publication timestamps or OOS independence.'
    }
    for path in sorted(list(ROOT.glob('*.py')) + list(ROOT.glob('config*.json')) + list((ROOT / 'data').glob('*.csv'))):
        evidence['hashes'][str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    uso = load('uso', 'close')
    nav = load('nav_160723', 'nav')
    op = load('160723', 'open')
    for conf, folder in [('config.json', 'output'), ('config_oos_9_3.json', 'output_oos_9_3'),
                         ('config_proxy_10_5.json', 'output_proxy_10_5'), ('config_proxy_9_3.json', 'output_proxy_9_3')]:
        cfg = json.loads((ROOT / conf).read_text())
        out, report = strategy.run(cfg)
        out = out.set_index('date')
        saved = pd.read_csv(ROOT / folder / 'positions.csv', parse_dates=['date']).set_index('date')
        same_index = saved.index.equals(out.index)
        errors = {c: float((out[c] - saved[c]).abs().max()) for c in ['pnl', 'premium', 'held_position']}
        stored_report = json.loads((ROOT / folder / 'metrics.json').read_text())
        stored_oos = json.loads((ROOT / folder / 'oos_metrics.json').read_text()) if (ROOT / folder / 'oos_metrics.json').exists() else None
        r = {'same_saved_index': same_index, 'max_saved_abs_errors': errors,
             'metric_max_abs_error': max(abs(report['strategy'][k] - stored_report['strategy'][k]) for k in ['cagr', 'sharpe', 'calmar', 'mdd']),
             'original_full': report['strategy'], 'original_train': summarize(out.pnl.loc[:'2021-12-31'], out.held_position.loc[:'2021-12-31']),
             'original_oos': summarize(out.pnl.loc['2022-01-01':], out.held_position.loc['2022-01-01':])}
        if stored_oos:
            r['oos_max_abs_error'] = max(abs(r['original_oos'][k] - stored_oos['oos'][k]) for k in ['cagr', 'sharpe', 'calmar', 'mdd'])
        # Keep signal formula fixed: settle trades one close later, then earn returns.
        late = out.target_position.shift(2).fillna(0)
        pnl_late = late * out.ret - cfg['execution']['fee'] * late.diff().abs().fillna(late.abs())
        r['next_close_diagnostic_full'] = summarize(pnl_late, late)
        r['next_close_diagnostic_oos'] = summarize(pnl_late.loc['2022-01-01':], late.loc['2022-01-01':])
        # Close-marked accounting for next-open execution: old holdings earn overnight,
        # new holdings earn intraday. Cost charged on turnover at the open.
        opening = op.reindex(out.index)
        old = out.target_position.shift(2).fillna(0)
        new = out.target_position.shift(1).fillna(0)
        overnight = opening / out.close.shift(1) - 1
        intraday = out.close / opening - 1
        gross_factor = (1 + old * overnight) * (1 + new * intraday)
        pnl_open = gross_factor - 1 - cfg['execution']['fee'] * (new - old).abs()
        r['next_open_diagnostic_full'] = summarize(pnl_open, new)
        r['next_open_diagnostic_oos'] = summarize(pnl_open.loc['2022-01-01':], new.loc['2022-01-01':])
        # Prefix invariance detects future rows influencing earlier results; it cannot
        # establish that observation-date-stamped inputs were actually published.
        r['prefix_max_abs_error'] = {}
        for end in ['2021-12-31', '2024-12-31']:
            prefix, _ = strategy.run(dict(cfg, end=end))
            prefix = prefix.set_index('date')
            r['prefix_max_abs_error'][end] = float((prefix[['premium', 'target_position', 'pnl']] - out.loc[:end, ['premium', 'target_position', 'pnl']]).abs().max().max())
        if cfg['premium'].get('nav_source') == 'proxy_uso':
            u = uso.pct_change().reindex(out.index).ffill().shift(1)
            nav_base = nav.reindex(out.index).ffill().shift(3)
            # Diagnostic: latest completed US level strictly before each CN date,
            # divided by US level corresponding to the actual base NAV valuation date.
            source_nav_date = pd.Series(nav.index, index=nav.index).reindex(out.index).ffill().shift(3)
            end_dates = out.index - pd.Timedelta(days=1)
            end_levels = uso.reindex(end_dates, method='ffill').set_axis(out.index)
            start_levels = pd.Series([uso.asof(t) if pd.notna(t) else np.nan for t in source_nav_date], index=out.index)
            aligned_nav = nav_base * end_levels / start_levels
            aligned_prem = out.close / aligned_nav - 1
            state, weights = 1.0, []
            for p in aligned_prem:
                if pd.notna(p):
                    if p > cfg['premium']['block']:
                        state = 0.0
                    elif p < cfg['premium']['reenter']:
                        state = 1.0
                weights.append(state)
            target = out.base_position * pd.Series(weights, index=out.index)
            held = target.shift(1).fillna(0)
            pnl = held * out.ret - cfg['execution']['fee'] * held.diff().abs().fillna(held.abs())
            r['calendar_diagnostic'] = {
                'definition': 'USO level ratio on actual NAV valuation date to latest US date < CN date; same original execution; NOT a PIT-certified replacement',
                'differing_target_days': int((target != out.target_position).sum()),
                'full': summarize(pnl, held), 'oos': summarize(pnl.loc['2022-01-01':], held.loc['2022-01-01':]),
                'example': pd.DataFrame({'old_u': u, 'old_proxy': out.close / (1 + out.premium), 'aligned_proxy': aligned_nav,
                                         'base_nav_date': source_nav_date}).loc['2024-07-03':'2024-07-09'].reset_index().astype(str).to_dict('records')}
        current, _ = strategy.run(dict(cfg, end='2026-10-29'))
        r['latest_from_snapshot'] = current.iloc[-1][['date', 'premium', 'target_position']].astype(str).to_dict()
        evidence['configs'][conf] = r
    idx = out.index
    c = load('cushing', 'value')
    roll = c.rolling(52).mean()
    cs = (roll - roll.shift(4) > 0).astype(float).where(roll.notna())
    a = cs.reindex(idx).ffill().shift(6)
    b = cs.reindex(idx, method='ffill').shift(6)
    evidence['cushing_calendar'] = {'dropped_weekly_observations': int(((c.index >= idx[0]) & (c.index <= idx[-1]) & ~c.index.isin(idx)).sum()),
                                    'different_signal_days': int(((a != b) & a.notna() & b.notna()).sum())}
    dates = pd.date_range('2020-01-01', periods=3)
    evidence['metric_initial_loss_example'] = {'pnl': [-0.1, 0, 0], 'reported_mdd': strategy.metrics(pd.Series([-0.1, 0, 0], index=dates), pd.Series(1., index=dates))['mdd'], 'correct_mdd_with_initial_capital': -0.1}
    import audit_lag3
    cfg = json.loads((ROOT / 'config.json').read_text())
    official, _ = strategy.run(cfg)
    official = official.set_index('date')
    alternate = audit_lag3.close_pnl(official.close, official.target_position)
    delta = alternate - official.pnl
    evidence['enhancement_accounting'] = {'different_pnl_days': int((delta.abs() > 1e-12).sum()), 'max_daily_abs_error': float(delta.abs().max()),
                                          'cause': 'enhancement fees use target.diff on decision day; strategy fees use held.diff on next return day'}
    bh = official.ret - cfg['execution']['fee'] * pd.Series(1., index=official.index).diff().abs().fillna(1.)
    evidence['buy_hold_initial_fee'] = {'first_pnl_is_nan': bool(pd.isna(bh.iloc[0])), 'gross_final': float((1 + official.ret).prod()), 'reported_net_final': float((1 + bh).prod())}
    evidence['data_quality'] = {}
    for path in sorted((ROOT / 'data').glob('*.csv')):
        df = pd.read_csv(path)
        if 'date' in df:
            evidence['data_quality'][path.name] = {'rows': len(df), 'duplicate_dates': int(df.date.duplicated().sum()), 'last_date': str(df.date.max())}
    mismatches = []
    for line in (ROOT / 'data' / 'SHA256SUMS').read_text().splitlines():
        expected, name = line.split(maxsplit=1)
        actual = hashlib.sha256((ROOT / 'data' / name.strip()).read_bytes()).hexdigest()
        if actual != expected:
            mismatches.append(name)
    evidence['manifest_mismatches'] = mismatches
    output = Path(__file__).with_name('evidence.json')
    output.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + '\n')
    print(output)
    for name, result in evidence['configs'].items():
        print(name, json.dumps({k: result[k] for k in ['original_oos', 'next_close_diagnostic_oos', 'next_open_diagnostic_oos']}))


if __name__ == '__main__':
    main()
