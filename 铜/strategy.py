#!/usr/bin/env python3
"""GTJA series 28 copper public-macro 50/50 blend.

Baseline macro4: DXY z250 (-), VIX z60 (-), ISM z250 (+), CFTC net z250 (+).
Optimised macro4: VIX 20d-change z60 (-), ISM 250d level rank (+),
DXY 120d-change rank520 with 0.5 deadband (-), CFTC level z60 (+).
Final position = sign(0.5*baseline + 0.5*optimised), 0/1/-1, 1x,
0.03% round-trip, t+1 close, additive PnL.

This is a B-level public-macro subset, not the full 14-factor report
reproduction. It excludes TC, social inventories, scrap spread, copper-foil
processing fee, LME/COMEX stocks and the report's 7 price-volume factors.
"""
from __future__ import annotations
import argparse, json, pathlib
import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent
DATA = ROOT / 'data'


def load_cu():
    d = pd.read_csv(DATA/'CU0_main.csv', parse_dates=['日期'])
    d = d.rename(columns={'日期':'date','开盘价':'open','最高价':'high','最低价':'low','收盘价':'close','成交量':'volume'})
    d = d.drop_duplicates('date').set_index('date').sort_index()
    for c in ['open','high','low','close','volume']:
        d[c] = pd.to_numeric(d[c], errors='coerce')
    d = d.dropna(subset=['close'])
    r = d.close.pct_change().clip(-0.06, 0.06)
    scale = (1+r.fillna(0)).cumprod()/d.close
    out = d.copy()
    for c in ['open','high','low','close']:
        out[c] = d[c]*scale
    return out


def load_series(path, col, date_col):
    d = pd.read_csv(DATA/path, parse_dates=[date_col])
    s = d.set_index(date_col)[col].dropna().sort_index()
    return s[~s.index.duplicated(keep='last')]


def z(x, w, direction, db=0.0):
    m = x.rolling(w, min_periods=max(10, w//2)).mean()
    s = x.rolling(w, min_periods=max(10, w//2)).std()
    v = (x-m)/s*direction
    return pd.Series(np.where(v.abs() > db, np.sign(v), 0), index=x.index).fillna(0)


def chg_z(x, w, k, direction, db=0.0):
    c = x-x.shift(k)
    v = c/c.rolling(w, min_periods=max(10, w//2)).std()*direction
    return pd.Series(np.where(v.abs() > db, np.sign(v), 0), index=x.index).fillna(0)


def rank_sig(x, w, direction, db=0.0):
    r = x.rolling(w, min_periods=max(10, w//2)).apply(lambda a: (a[-1] > a).mean(), raw=True)*2-1
    v = r*direction
    return pd.Series(np.where(v.abs() > db, np.sign(v), 0), index=x.index).fillna(0)


def chg_rank(x, w, k, direction, db=0.0):
    c = x-x.shift(k)
    r = c.rolling(w, min_periods=max(10, w//2)).apply(lambda a: (a[-1] > a).mean(), raw=True)*2-1
    v = r*direction
    return pd.Series(np.where(v.abs() > db, np.sign(v), 0), index=x.index).fillna(0)


def build():
    D = load_cu(); idx = D.index
    dxy = load_series('eastmoney_usd_index_udi.csv', 'close', 'date').reindex(idx, method='ffill')
    vix = load_series('cboe_VIX_History.csv', 'close', 'date').reindex(idx, method='ffill')
    ism = load_series('ism_manufacturing_pmi_eastmoney.csv', 'value', 'publish_date').reindex(idx, method='ffill')
    cftc = load_series('cftc_copper_net.csv', 'net', 'pub').reindex(idx, method='ffill')

    base = pd.DataFrame({
        'dxy': z(dxy, 250, -1),
        'vix': z(vix, 60, -1),
        'ism': z(ism, 250, +1),
        'cftc': z(cftc, 250, +1),
    })
    opt = pd.DataFrame({
        'dxy': chg_rank(dxy, 520, 120, -1, 0.5),
        'vix': chg_z(vix, 60, 20, -1),
        'ism': rank_sig(ism, 250, +1),
        'cftc': z(cftc, 60, +1),
    })
    b = np.sign(base.mean(axis=1)); o = np.sign(opt.mean(axis=1))
    pos = np.sign(0.5*b + 0.5*o).fillna(0)
    return pos, {'baseline': base, 'optimized': opt, 'cu': D}


def metrics(pos, D, cost=0.0003, ann=252):
    p = pos.reindex(D.index).fillna(0)
    ret = D.close.pct_change()
    pnl = p.shift(1).fillna(0)*ret - cost*p.diff().abs().fillna(0)
    pnl = pnl.dropna(); nav = 1+pnl.cumsum(); dd = (nav/nav.cummax()-1).min()
    active = pnl[p.shift(1).reindex(pnl.index).fillna(0) != 0]
    return dict(n=len(pnl), cagr=float(pnl.mean()*ann), vol=float(pnl.std()*np.sqrt(ann)),
                sharpe=float(pnl.mean()/pnl.std()*np.sqrt(ann)) if pnl.std()>0 else float('nan'),
                mdd=float(dd), calmar=float(pnl.mean()*ann/abs(dd)) if dd<0 else float('nan'),
                win=float((active>0).mean()) if len(active) else float('nan'),
                final=float(nav.iloc[-1]))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--output', default=str(ROOT/'output'))
    args = ap.parse_args()
    pos, parts = build(); D = parts['cu']
    windows = {'in_sample_2016_2024': ('2016-01-01','2024-12-31'),
               'validation_2019_2021': ('2019-01-01','2021-12-31'),
               'pseudo_oos_2022_2024': ('2022-01-01','2024-12-31'),
               'holdout_2025_2026': ('2025-01-01','2026-10-20'),
               'oos_2022_2026': ('2022-01-01','2026-10-20')}
    res = {k: metrics(pos.loc[a:b], D.loc[a:b]) for k,(a,b) in windows.items()}
    print(json.dumps(res, ensure_ascii=False, indent=1))
    out = pathlib.Path(args.output); out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({'date':D.index,'position':pos.values}).to_csv(out/'positions.csv', index=False)
    (out/'metrics.json').write_text(json.dumps(res, ensure_ascii=False, indent=1))
    (out/'parameters.json').write_text(json.dumps({
        'blend':'sign(0.5*baseline_macro4 + 0.5*optimized_macro4)',
        'baseline':{'dxy':'z250 -1','vix':'z60 -1','ism':'z250 +1','cftc':'z250 +1'},
        'optimized':{'dxy':'chg_rank520/120 db0.5 -1','vix':'chg_z60/20 -1','ism':'level_rank250 +1','cftc':'z60 +1'},
        'cost':'0.03% round-trip','leverage':1.0}, ensure_ascii=False, indent=1))

if __name__ == '__main__':
    main()
