#!/usr/bin/env python3
"""GTJA series 26 best all-factor soybean-meal strategy.

Frozen model: sign(0.8 * fundamental_5 + 0.2 * price_volume_9).
The fundamental block is selected on 2016-2021; the PV block on 2010-2021.
All signals are 0/1/-1, 1x leverage, 0.03% round-trip cost, additive returns.

This is a research reconstruction, not a live mandate.  The source report does
not disclose the 0/1/-1 thresholds; the mappings here are transparent proxies.
"""
from __future__ import annotations
import argparse, json, pathlib
import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent
DATA = ROOT / 'data'


# ---------- data ----------
def load_main(name: str) -> pd.DataFrame:
    a = pd.read_csv(DATA / f'{name}_main_sina.csv', parse_dates=['日期'])
    b = pd.read_csv(DATA / f'{name}_main_2025_2026.csv', parse_dates=['日期'])
    d = pd.concat([a, b]).rename(columns={'日期':'date','开盘价':'open','最高价':'high','最低价':'low','收盘价':'close','成交量':'volume'})
    d = d.drop_duplicates('date').set_index('date').sort_index()
    for c in ['open','high','low','close','volume']:
        d[c] = pd.to_numeric(d[c], errors='coerce')
    d = d.dropna(subset=['close'])
    # remove the known far-contract artifact and clip roll jumps
    if pd.Timestamp('2014-10-08') in d.index:
        d.loc['2014-10-08', ['open','high','low','close']] = [2780, 2795, 2760, 2790]
    r = d.close.pct_change().clip(-0.06, 0.06)
    scale = (1 + r.fillna(0)).cumprod() / d.close
    out = d.copy()
    for c in ['open','high','low','close']:
        out[c] = d[c] * scale
    return out


def load_weekly(path, col):
    d = pd.read_csv(path)
    d = d.rename(columns={'publish':'pub', col:'value'})
    d['pub'] = pd.to_datetime(d['pub'])
    return d.set_index('pub')['value'].dropna().sort_index()


# ---------- transforms ----------
def ema(x, n):
    return x.ewm(span=n, adjust=False).mean()


def kama(price, n=10, fast=2, slow=30):
    change = (price - price.shift(n)).abs()
    vol = price.diff().abs().rolling(n).sum()
    er = (change / vol).replace([np.inf, -np.inf], np.nan).fillna(0)
    sc = (er * (2/(fast+1)) + (1-er) * (2/(slow+1))) ** 2
    out, prev = [], price.iloc[0]
    for p, s in zip(price.values, sc.values):
        prev = prev + s * (p - prev); out.append(prev)
    return pd.Series(out, index=price.index)


def state(entry_long, entry_short, index):
    out, cur = [], 0
    for l, s in zip(entry_long.values, entry_short.values):
        if l: cur = 1
        elif s: cur = -1
        out.append(cur)
    return pd.Series(out, index=index)


def deadband(z, db):
    return pd.Series(np.where(z.abs() > db, np.sign(z), 0), index=z.index)


def level_z(x, w, direction):
    m = x.rolling(w, min_periods=max(10, w//2)).mean()
    s = x.rolling(w, min_periods=max(10, w//2)).std()
    return deadband(((x-m)/s) * direction, 0)


def level_rank(x, w, direction):
    r = x.rolling(w, min_periods=max(10, w//2)).apply(lambda a: (a[-1] > a).mean(), raw=True) * 2 - 1
    return deadband(r * direction, 0)


def chg_rank(x, w, k, direction):
    ch = x - x.shift(k)
    r = ch.rolling(w, min_periods=max(10, w//2)).apply(lambda a: (a[-1] > a).mean(), raw=True) * 2 - 1
    return deadband(r * direction, 0)


# ---------- price-volume factors ----------
def pv_signal(D: pd.DataFrame) -> pd.DataFrame:
    out = {}
    # TRIX n=6, fast=10, slow=30, db=0.0005
    ex = ema(ema(ema(D.close, 6), 6), 6); trix = ex/ex.shift(1) - 1
    out['trix'] = deadband(trix.rolling(10).mean() - trix.rolling(30).mean(), 0.0005)
    # CCI n=20, entry=150, trend direction
    tp = (D.high + D.low + D.close)/3; ma = tp.rolling(20).mean(); md = (tp-ma).abs().rolling(20).mean()
    cci = (tp-ma)/(0.015*md)
    out['cci'] = state(cci < -150, cci > 150, D.index) * 1
    # MA 10/20, 1% deadband
    sp = D.close.rolling(10).mean() - D.close.rolling(20).mean()
    out['ma'] = deadband(sp/D.close, 0.01)
    # Bollinger 20/2.5 breakout
    ma20 = D.close.rolling(20).mean(); sd20 = D.close.rolling(20).std()
    out['boll'] = state(D.close > ma20 + 2.5*sd20, D.close < ma20 - 2.5*sd20, D.index)
    # KAMA 20 slope, 0.5% deadband
    k = kama(D.close, 20)
    out['kama'] = deadband(k.pct_change(), 0.005)
    # volatility 40, expansion
    v = D.close.pct_change().rolling(40).std()
    out['vol'] = deadband(v - v.rolling(30).mean(), 0)
    # median MA 3/15
    med = (D.high + D.low)/2
    out['medma'] = deadband((med.rolling(3).mean() - med.rolling(15).mean())/med, 0)
    # Chaikin 5/10
    hl = (D.high - D.low).replace(0, np.nan)
    adl = (((2*D.close - D.high - D.low)/hl) * D.volume).fillna(0).cumsum()
    spc = ema(adl, 5) - ema(adl, 10)
    out['chaikin'] = deadband(spc / spc.rolling(250).std(), 0)
    # intraday momentum 10, MA mode
    im = (D.high + D.low)/2/D.open - 1
    out['im'] = deadband(im - im.rolling(10).mean(), 0)
    return pd.DataFrame(out).fillna(0)


# ---------- fundamental factors ----------
def fund_signal(D: pd.DataFrame, A, Y, RM) -> pd.DataFrame:
    idx = D.index
    crush = load_weekly(DATA/'factor_soy_inventory_combined.csv', 'value').reindex(idx, method='ffill')
    port = load_weekly(DATA/'soy_port_inventory_weekly.csv', 'value').reindex(idx, method='ffill')
    basis = pd.concat([pd.read_csv(DATA/'m_basis_2016_2024.csv'), pd.read_csv(DATA/'m_basis_2025_2026.csv')], ignore_index=True)
    basis['date'] = pd.to_datetime(basis.date)
    basis = basis.set_index('date')['dom_basis_rate'].sort_index().reindex(idx, method='ffill')
    common = idx.intersection(RM.index); spread = (D.loc[common,'close']/RM.loc[common,'close']).reindex(idx, method='ffill')
    c2 = idx.intersection(A.index).intersection(Y.index)
    margin = ((D.loc[c2,'close']*0.785 + Y.loc[c2,'close']*0.185 - A.loc[c2,'close'])/A.loc[c2,'close']).reindex(idx, method='ffill')
    out = pd.DataFrame({
        'basis': level_z(basis, 250, +1),
        'port': level_rank(port, 520, -1),
        'margin': level_z(margin, 250, -1),
        'crush': level_rank(crush, 520, -1),
        'spread': chg_rank(spread, 60, 20, +1),
    })
    return out.fillna(0)


# ---------- metrics ----------
def metrics(pos: pd.Series, D: pd.DataFrame, cost=0.0003, ann=252) -> dict:
    ret = D.close.pct_change()
    p = pos.reindex(ret.index).fillna(0)
    pnl = p.shift(1).fillna(0)*ret - cost*p.diff().abs().fillna(0)
    pnl = pnl.dropna(); nav = 1 + pnl.cumsum()
    dd = (nav/nav.cummax()-1).min()
    cagr = pnl.mean()*ann; vol = pnl.std()*np.sqrt(ann)
    return dict(n=len(pnl), cagr=float(cagr), vol=float(vol),
                sharpe=float(pnl.mean()/pnl.std()*np.sqrt(ann)) if pnl.std()>0 else float('nan'),
                mdd=float(dd), calmar=float(cagr/abs(dd)) if dd<0 else float('nan'),
                win=float((pnl>0).mean()), final=float(nav.iloc[-1]))


def build() -> tuple[pd.Series, dict]:
    M = load_main('M0'); A = load_main('A0'); Y = load_main('Y0'); RM = load_main('RM0')
    F = fund_signal(M, A, Y, RM); P = pv_signal(M)
    fund = np.sign(F.mean(axis=1)); pv = np.sign(P.mean(axis=1))
    final = np.sign(0.8*fund + 0.2*pv).fillna(0)
    return final, {'fundamental': F, 'price_volume': P, 'M': M}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', default=str(ROOT/'output'))
    args = ap.parse_args()
    pos, parts = build(); M = parts['M']
    windows = {'train_2016_2021': ('2016-01-01','2021-12-31'),
               'pseudo_oos_2022_2024': ('2022-01-01','2024-12-31'),
               'holdout_2025_2026': ('2025-01-01','2026-10-20'),
               'oos_2022_2026': ('2022-01-01','2026-10-20')}
    res = {k: metrics(pos.loc[a:b], M.loc[a:b]) for k,(a,b) in windows.items()}
    print(json.dumps(res, ensure_ascii=False, indent=1))
    out = pathlib.Path(args.output); out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({'date':M.index,'position':pos.values}).to_csv(out/'positions.csv', index=False)
    (out/'metrics.json').write_text(json.dumps(res, ensure_ascii=False, indent=1))
    (out/'parameters.json').write_text(json.dumps({
        'blend':'sign(0.8*fundamental_5 + 0.2*price_volume_9)',
        'fundamental':{'basis':'level_z 250 +1','port':'level_rank 520 -1','margin':'level_z 250 -1','crush':'level_rank 520 -1','spread':'chg_rank 60/20 +1'},
        'price_volume':{'trix':'n6 fast10 slow30 db0.0005','cci':'n20 entry150 dir+1','ma':'10/20 db0.01','boll':'20/2.5','kama':'n20 slope db0.005','vol':'n40 expand db0','medma':'3/15 db0','chaikin':'5/10 db0','im':'n10 ma db0'},
        'cost':'0.03% round-trip','leverage':1.0}, ensure_ascii=False, indent=1))

if __name__ == '__main__':
    main()
