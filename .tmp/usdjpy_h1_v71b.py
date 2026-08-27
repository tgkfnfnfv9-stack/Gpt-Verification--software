import csv
import importlib.util
import json
import math
from datetime import datetime
from pathlib import Path

# Reuse the exact GBPJPY V7 reconstruction that produced the published V7 metrics.
spec = importlib.util.spec_from_file_location('m', '/tmp/gbpjpy_h1_v8_macro.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
b = m.b

OUT = Path('results')
OUT.mkdir(exist_ok=True)

DMI_PERIOD = 14
DMI_RATIO_MIN = 1.10


def dmi(bars, period=14):
    n = len(bars)
    tr = [0.0] * n
    pdm = [0.0] * n
    mdm = [0.0] * n
    plus_di = [None] * n
    minus_di = [None] * n
    ratio = [None] * n

    if n == 0:
        return plus_di, minus_di, ratio

    tr[0] = bars[0].high - bars[0].low
    for i in range(1, n):
        up = bars[i].high - bars[i - 1].high
        down = bars[i - 1].low - bars[i].low
        pdm[i] = up if up > down and up > 0 else 0.0
        mdm[i] = down if down > up and down > 0 else 0.0
        pc = bars[i - 1].close
        tr[i] = max(
            bars[i].high - bars[i].low,
            abs(bars[i].high - pc),
            abs(bars[i].low - pc),
        )

    if n <= period:
        return plus_di, minus_di, ratio

    # Wilder smoothing. Ratios are invariant to using sums vs averages.
    sm_tr = sum(tr[1:period + 1])
    sm_pdm = sum(pdm[1:period + 1])
    sm_mdm = sum(mdm[1:period + 1])

    for i in range(period, n):
        if i > period:
            sm_tr = sm_tr - sm_tr / period + tr[i]
            sm_pdm = sm_pdm - sm_pdm / period + pdm[i]
            sm_mdm = sm_mdm - sm_mdm / period + mdm[i]

        if sm_tr <= 0:
            continue
        p = 100.0 * sm_pdm / sm_tr
        q = 100.0 * sm_mdm / sm_tr
        plus_di[i] = p
        minus_di[i] = q
        if q > 0:
            ratio[i] = p / q
        elif p > 0:
            ratio[i] = float('inf')

    return plus_di, minus_di, ratio


def fmt_metrics(ts):
    return b.fmt(b.metrics(ts))


def sub(ts, a, z, bars):
    return b.subset(ts, a, z, bars)


def year_periods():
    return [
        ('2019-20', '2019-08-27', '2020-08-27'),
        ('2020-21', '2020-08-27', '2021-08-27'),
        ('2021-22', '2021-08-27', '2022-08-27'),
        ('2022-23', '2022-08-27', '2023-08-27'),
        ('2023-24', '2023-08-27', '2024-08-27'),
        ('2024-25', '2024-08-27', '2025-08-27'),
        ('2025-26', '2025-08-27', '2026-08-27'),
    ]


def candle_json(x):
    return {
        'time': x.dt.isoformat(timespec='seconds') + '+00:00',
        'open': round(x.open, 6),
        'high': round(x.high, 6),
        'low': round(x.low, 6),
        'close': round(x.close, 6),
        'volume': round(x.volume, 4),
    }


def main():
    bid = b.h1(b.load('data/USDJPY_M15_bid.csv'))
    ask = b.h1(b.load('data/USDJPY_M15_ask.csv'))
    if not bid or not ask:
        raise RuntimeError('USDJPY BID/ASK data missing after H1 aggregation')

    closes = [x.close for x in bid]
    e20 = b.ema(closes, 20)
    e50 = b.ema(closes, 50)
    a14 = b.atr(bid, 14)
    a50 = b.atr(bid, 50)
    rv = b.rvol_series(bid, 20)

    # Exact V7 technical setup/entry logic.
    base_events = m.detect2(bid, e20, e50, a14, a50, rv, m.V6P)
    base_ts = m.simulate_v7(bid, ask, base_events, a14, m.V7X)

    plus_di, minus_di, dmi_ratio = dmi(bid, DMI_PERIOD)

    # V7.1B: V7 setup unchanged; immediately before entry, require +DI14/-DI14 >= 1.10.
    v71b_events = []
    for e in base_events:
        i = e['entry_i'] - 1  # completed H1 bar immediately before next-H1 ASK-open entry
        if i < 0 or i >= len(dmi_ratio):
            continue
        r = dmi_ratio[i]
        if r is not None and r >= DMI_RATIO_MIN:
            ee = dict(e)
            ee['dmi_i'] = i
            ee['plus_di14'] = plus_di[i]
            ee['minus_di14'] = minus_di[i]
            ee['dmi_ratio'] = r
            v71b_events.append(ee)

    v71b_ts = m.simulate_v7(bid, ask, v71b_events, a14, m.V7X)

    periods = {
        'full_7y': ('2019-08-27', '2026-08-27'),
        'latest_2y': ('2024-08-27', '2026-08-27'),
        'covid_2020_21': ('2020-08-27', '2021-08-27'),
        'recent_2025_26': ('2025-08-27', '2026-08-27'),
    }
    for name, a, z in year_periods():
        periods['year_' + name.replace('-', '_')] = (a, z)

    v7_metrics = {k: fmt_metrics(sub(base_ts, a, z, bid)) for k, (a, z) in periods.items()}
    v71b_metrics = {k: fmt_metrics(sub(v71b_ts, a, z, bid)) for k, (a, z) in periods.items()}

    yearly = []
    for name, a, z in year_periods():
        yearly.append({
            'period': name,
            'v7': fmt_metrics(sub(base_ts, a, z, bid)),
            'v7_1b': fmt_metrics(sub(v71b_ts, a, z, bid)),
        })

    # Count setup candidates before non-overlap simulation too, to make filtering transparent.
    def count_events(a, z, evs):
        aa = datetime.fromisoformat(a)
        zz = datetime.fromisoformat(z)
        return sum(1 for e in evs if aa <= bid[e['entry_i']].dt < zz)

    event_counts = {
        k: {
            'v7_detected_setups': count_events(a, z, base_events),
            'v7_1b_detected_setups': count_events(a, z, v71b_events),
        }
        for k, (a, z) in periods.items()
    }

    summary = {
        'data_source': 'Dukascopy JForex/Jetta via dukascopy-go v0.2.0, USDJPY M15 BID+ASK aggregated to H1',
        'period': '2019-08-27 ～ 2026-08-26',
        'comparison': 'USDJPY H1 V7 vs V7.1B DMI Strong; all V7 parameters unchanged',
        'v7_entry_params': m.V6P,
        'v7_exit': m.V7X,
        'v7_1b_additional_filter': {
            'indicator': 'DMI14',
            'condition': '+DI14 / -DI14 >= 1.10',
            'timing': 'completed H1 bar immediately before entry; entry remains next H1 ASK open',
            'price_source': 'H1 BID OHLC',
            'future_data_used': False,
        },
        'metrics': {
            'v7': v7_metrics,
            'v7_1b': v71b_metrics,
        },
        'yearly': yearly,
        'detected_setup_counts': event_counts,
        'notes': [
            'This is a zero-parameter-transfer test from GBPJPY to USDJPY.',
            'V7.1B only adds the DMI direction-strength filter; Sweep/Flush/Recovery/Breakout/Retest, RVOL, ATR regime and V7 exits are unchanged.',
            'BUY entry uses the next H1 ASK open; SL/TP/TIME/RANGE exit evaluation uses BID prices via the published V7 simulator.',
            'No swap/rollover financing is included, matching the published V7 research limitation.',
        ],
    }

    (OUT / 'USDJPY_H1_V7_vs_V7_1B_summary.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8'
    )

    # Human-friendly trade CSV for all 7 years.
    with open(OUT / 'USDJPY_H1_V7_1B_trades.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow([
            'no', 'entry_time_utc', 'exit_time_utc', 'entry_price', 'exit_price',
            'stop', 'target', 'r', 'result', 'exit_reason', '+di14', '-di14', 'di_ratio'
        ])
        for no, t in enumerate(v71b_ts, 1):
            e = t['event']
            w.writerow([
                no,
                bid[t['entry_i']].dt.isoformat(timespec='seconds'),
                bid[t['exit_i']].dt.isoformat(timespec='seconds'),
                round(t['entry_price'], 6), round(t['exit_price'], 6),
                round(t['stop'], 6), round(t['target'], 6), round(t['r'], 6),
                t['result'], t['exit_reason'],
                round(e.get('plus_di14', 0.0), 6),
                round(e.get('minus_di14', 0.0), 6),
                'inf' if math.isinf(e.get('dmi_ratio', 0.0)) else round(e.get('dmi_ratio', 0.0), 6),
            ])

    # Viewer JSON for latest 2 years.
    si = next(i for i, x in enumerate(bid) if x.dt >= datetime(2024, 8, 27))
    ei = next((i for i, x in enumerate(bid) if x.dt >= datetime(2026, 8, 27)), len(bid))
    cb = bid[si:ei]
    cid = 'usdjpy_h1_v7_1b'

    latest_trades = sub(v71b_ts, '2024-08-27', '2026-08-27', bid)
    viewer_trades = []
    for no, t in enumerate(latest_trades, 1):
        e = t['event']
        nt = {
            'no': no,
            'chart_id': cid,
            'side': 'BUY',
            'entry_i': t['entry_i'] - si,
            'exit_i': t['exit_i'] - si,
            'entry_price': round(t['entry_price'], 6),
            'exit_price': round(t['exit_price'], 6),
            'stop': round(t['stop'], 6),
            'target': round(t['target'], 6),
            'r': round(t['r'], 6),
            'result': 'WIN' if t['r'] > 0 else 'LOSS',
            'confidence': None,
            'setup': 'USDJPY H1 V7.1B DMI Strong',
            'note': (
                f"exit={t['exit_reason']}, +DI14={e.get('plus_di14', 0):.2f}, "
                f"-DI14={e.get('minus_di14', 0):.2f}, ratio={e.get('dmi_ratio', 0):.3f}"
            ),
        }
        if 0 <= nt['entry_i'] <= nt['exit_i'] < len(cb):
            viewer_trades.append(nt)

    def finite_or_none(x):
        if x is None or not math.isfinite(x):
            return None
        return round(x, 6)

    chart = {
        'id': cid,
        'symbol': 'USDJPY',
        'timeframe': 'H1',
        'period': '2024-08-27 ～ 2026-08-26',
        'candles': [candle_json(x) for x in cb],
        'overlays': [
            {'kind': 'line', 'label': 'EMA20', 'values': [round(x, 6) for x in e20[si:ei]]},
            {'kind': 'line', 'label': 'EMA50', 'values': [round(x, 6) for x in e50[si:ei]]},
        ],
        'panes': [
            {
                'label': 'DMI14',
                'series': [
                    {'kind': 'line', 'label': '+DI14', 'values': [finite_or_none(x) for x in plus_di[si:ei]]},
                    {'kind': 'line', 'label': '-DI14', 'values': [finite_or_none(x) for x in minus_di[si:ei]]},
                    {'kind': 'line', 'label': '+DI/-DI', 'values': [finite_or_none(x) for x in dmi_ratio[si:ei]]},
                ],
            }
        ],
    }

    viewer = {
        'meta': {'report_title': 'USDJPY H1 V7.1B DMI Strong', 'status': '検証済み'},
        'strategy': {
            'strategy_id': 'USDJPY_H1_FLUSH_RECOVERY_V7_1B_DMI_STRONG',
            'name': 'Flush Recovery V7.1B DMI Strong',
            'hypothesis': 'V7の流動性Sweep後の上昇再開セットアップに、エントリー直前のDMI上方向優位を追加する。',
            'entry_logic': [
                'V7エントリー条件は変更なし',
                '+DI14 / -DI14 >= 1.10（エントリー直前の確定H1 BID足）',
                'Entryは次H1 ASK始値',
            ],
            'exit_logic': [
                'SL = Flush安値 - 0.10×ATR14',
                'TP = +2.50R',
                '最大保有30時間',
                '16時間後のV7レンジ撤退',
            ],
            'future_tests': ['GBPJPYとの銘柄間比較', '未使用期間・MT5ブローカーデータで再検証'],
        },
        'charts': [chart],
        'trades': viewer_trades,
        'notes': [json.dumps(summary, ensure_ascii=False)],
    }
    (OUT / 'USDJPY_H1_V7_1B_2y_viewer.json').write_text(
        json.dumps(viewer, ensure_ascii=False, separators=(',', ':')), encoding='utf-8'
    )

    print('=== USDJPY H1 V7 vs V7.1B ===')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
