#!/usr/bin/env python3
"""Phase 8 blind Discovery screen.

This runner intentionally cannot read Development, OOS, or Final Holdout rows.
Signals use completed BID bars. ASK bars are used only for spread and executable prices.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import json
import math
import random
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

WARMUP_START = datetime(2019, 7, 1)
DISCOVERY_START = datetime(2019, 8, 28)
DISCOVERY_END = datetime(2022, 8, 28)
SEED = 20260828
BAR_HORIZONS = (1, 3, 6)
CLOCK_HORIZONS = (4, 12, 24)
PRIMARY = "clock_12h"

ALL_SYMBOLS = (
    "AUDJPY", "AUDUSD", "EURGBP", "EURJPY", "EURUSD", "GBPJPY",
    "GBPUSD", "USDJPY", "XAUUSD", "XAGUSD", "BRENTCMDUSD", "LIGHTCMDUSD",
)
USD_SET = ("AUDUSD", "EURUSD", "GBPUSD", "USDJPY")
JPY_SET = ("AUDJPY", "EURJPY", "GBPJPY", "USDJPY")
METALS = ("XAUUSD", "XAGUSD")
COMMODITIES = ("XAUUSD", "XAGUSD", "BRENTCMDUSD", "LIGHTCMDUSD")
ENERGY = ("BRENTCMDUSD", "LIGHTCMDUSD")


@dataclass(frozen=True)
class Bar:
    dt: datetime
    bo: float
    bh: float
    bl: float
    bc: float
    ao: float
    ah: float
    al: float
    ac: float
    volume: float


@dataclass
class Series:
    symbol: str
    timeframe: str
    bars: list[Bar]
    times: list[datetime]
    index: dict[datetime, int]
    tr: list[float]
    atr: list[float | None]
    ema20: list[float]
    ema50: list[float]
    volume_ratio: list[float | None]
    rv12: list[float | None]
    rv_baseline: list[float | None]
    quiet_q20: list[float | None]
    dec_atr: list[int | None]
    dec_trend: list[int | None]
    dec_spread: list[int | None]
    dec_volume: list[int | None]


@dataclass(frozen=True)
class Signal:
    candidate_id: str
    symbol: str
    timeframe: str
    i: int
    side: str
    variant: str = "base"


def norm(value: str) -> str:
    return "".join(ch.lower() for ch in value if ch.isalnum())


def pick(fields: list[str], candidates: list[str]) -> str:
    mapped = {norm(field): field for field in fields}
    for candidate in candidates:
        if norm(candidate) in mapped:
            return mapped[norm(candidate)]
    for normalized, field in mapped.items():
        if any(normalized.endswith(norm(candidate)) for candidate in candidates):
            return field
    raise KeyError(f"Missing CSV column: {candidates}")


def parse_dt(value: str) -> datetime:
    text = str(value).strip().strip('"').replace("Z", "+00:00")
    try:
        numeric = float(text)
        if numeric > 1e12:
            return datetime.fromtimestamp(numeric / 1000, tz=timezone.utc).replace(tzinfo=None)
        if numeric > 1e9:
            return datetime.fromtimestamp(numeric, tz=timezone.utc).replace(tzinfo=None)
    except ValueError:
        pass
    parsed = datetime.fromisoformat(text)
    return parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed


def load_side(path: Path) -> dict[datetime, tuple[float, float, float, float, float]]:
    output: dict[datetime, tuple[float, float, float, float, float]] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        time_key = pick(fields, ["timestamp", "datetime", "time", "date"])
        open_key = pick(fields, ["open"])
        high_key = pick(fields, ["high"])
        low_key = pick(fields, ["low"])
        close_key = pick(fields, ["close"])
        try:
            volume_key = pick(fields, ["volume", "tick_volume"])
        except KeyError:
            volume_key = ""
        for row in reader:
            dt = parse_dt(row[time_key])
            if not (WARMUP_START <= dt < DISCOVERY_END):
                continue
            o, h, l, c = (float(row[key]) for key in (open_key, high_key, low_key, close_key))
            volume = float(row[volume_key]) if volume_key and row.get(volume_key) else 0.0
            if o <= 0 or h < max(o, c) or l > min(o, c):
                raise ValueError(f"Invalid OHLC in {path.name} at {dt.isoformat()}")
            output[dt] = (o, h, l, c, volume)
    return output


def load_pair(data_dir: Path, symbol: str, base_timeframe: str) -> list[Bar]:
    bid = load_side(data_dir / f"{symbol}_{base_timeframe}_bid.csv")
    ask = load_side(data_dir / f"{symbol}_{base_timeframe}_ask.csv")
    common = sorted(set(bid) & set(ask))
    if len(common) < 500:
        raise ValueError(f"Insufficient joined rows for {symbol} {base_timeframe}: {len(common)}")
    bars: list[Bar] = []
    for dt in common:
        b, a = bid[dt], ask[dt]
        if a[0] < b[0] or a[3] < b[3]:
            raise ValueError(f"Crossed BID/ASK at {symbol} {dt.isoformat()}")
        bars.append(Bar(dt, *b[:4], *a[:4], b[4]))
    return bars


def aggregate(source: list[Bar], hours: int) -> list[Bar]:
    grouped: dict[datetime, list[Bar]] = defaultdict(list)
    for bar in source:
        bucket_hour = (bar.dt.hour // hours) * hours
        key = bar.dt.replace(hour=bucket_hour, minute=0, second=0, microsecond=0)
        grouped[key].append(bar)
    output: list[Bar] = []
    for key, group in sorted(grouped.items()):
        group.sort(key=lambda item: item.dt)
        if len(group) != hours:
            continue
        if any(group[offset].dt != key + timedelta(hours=offset) for offset in range(hours)):
            continue
        output.append(Bar(
            key,
            group[0].bo, max(x.bh for x in group), min(x.bl for x in group), group[-1].bc,
            group[0].ao, max(x.ah for x in group), min(x.al for x in group), group[-1].ac,
            sum(x.volume for x in group),
        ))
    return output


def rolling_deciles(values: list[float | None], window: int = 240, minimum: int = 120) -> list[int | None]:
    result: list[int | None] = [None] * len(values)
    sorted_window: list[float] = []
    for i, value in enumerate(values):
        if i:
            previous = values[i - 1]
            if previous is not None and math.isfinite(previous):
                bisect.insort(sorted_window, previous)
        remove_i = i - window - 1
        if remove_i >= 0:
            old = values[remove_i]
            if old is not None and math.isfinite(old):
                sorted_window.pop(bisect.bisect_left(sorted_window, old))
        if value is not None and math.isfinite(value) and len(sorted_window) >= minimum:
            result[i] = min(9, int(10 * bisect.bisect_right(sorted_window, value) / len(sorted_window)))
    return result


def rolling_median(values: list[float | None], window: int, minimum: int) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    sorted_window: list[float] = []
    for i, value in enumerate(values):
        if i:
            previous = values[i - 1]
            if previous is not None and math.isfinite(previous):
                bisect.insort(sorted_window, previous)
        remove_i = i - window - 1
        if remove_i >= 0:
            old = values[remove_i]
            if old is not None and math.isfinite(old):
                sorted_window.pop(bisect.bisect_left(sorted_window, old))
        if len(sorted_window) >= minimum:
            result[i] = statistics.median(sorted_window)
    return result


def lagged_quantile(values: list[float], history: int, gap: int, quantile: float) -> list[float | None]:
    """Prior-only quantile of values[i-gap-history:i-gap]."""
    result: list[float | None] = [None] * len(values)
    sorted_window: list[float] = []
    for i in range(len(values)):
        add_i = i - gap - 1
        if add_i >= 0:
            bisect.insort(sorted_window, values[add_i])
        remove_i = i - gap - history - 1
        if remove_i >= 0:
            old = values[remove_i]
            sorted_window.pop(bisect.bisect_left(sorted_window, old))
        if len(sorted_window) == history:
            result[i] = sorted_window[int(quantile * (history - 1))]
    return result


def build_series(symbol: str, timeframe: str, bars: list[Bar]) -> Series:
    tr: list[float] = []
    for i, bar in enumerate(bars):
        previous_close = bars[i - 1].bc if i else bar.bc
        tr.append(max(bar.bh - bar.bl, abs(bar.bh - previous_close), abs(bar.bl - previous_close)))
    atr: list[float | None] = [None] * len(bars)
    for i in range(14, len(bars)):
        atr[i] = sum(tr[i - 14:i]) / 14
    ema20: list[float] = []
    ema50: list[float] = []
    for i, bar in enumerate(bars):
        ema20.append(bar.bc if not i else (2 / 21) * bar.bc + (19 / 21) * ema20[-1])
        ema50.append(bar.bc if not i else (2 / 51) * bar.bc + (49 / 51) * ema50[-1])
    volume_median = rolling_median([bar.volume for bar in bars], 20, 10)
    volume_ratio = [
        (bars[i].volume / volume_median[i]) if volume_median[i] and volume_median[i] > 0 else None
        for i in range(len(bars))
    ]
    returns: list[float | None] = [None]
    for i in range(1, len(bars)):
        returns.append(math.log(bars[i].bc / bars[i - 1].bc))
    rv12: list[float | None] = [None] * len(bars)
    for i in range(12, len(bars)):
        sample = [x for x in returns[i - 11:i + 1] if x is not None]
        rv12[i] = statistics.stdev(sample) if len(sample) >= 2 else None
    rv_baseline = rolling_median(rv12, 120, 60)
    quiet_q20 = lagged_quantile(tr, history=240, gap=8, quantile=0.20)
    trend = [
        abs(bars[i - 1].bc - bars[i - 9].bc) / atr[i]
        if i >= 9 and atr[i] and atr[i] > 0 else None
        for i in range(len(bars))
    ]
    spread = [
        (bars[i - 1].ac - bars[i - 1].bc) / atr[i]
        if i and atr[i] and atr[i] > 0 else None
        for i in range(len(bars))
    ]
    return Series(
        symbol, timeframe, bars, [bar.dt for bar in bars], {bar.dt: i for i, bar in enumerate(bars)}, tr, atr, ema20, ema50,
        volume_ratio, rv12, rv_baseline, quiet_q20,
        rolling_deciles(atr), rolling_deciles(trend), rolling_deciles(spread), rolling_deciles(volume_ratio),
    )


def body_fraction(bar: Bar) -> float:
    return abs(bar.bc - bar.bo) / (bar.bh - bar.bl) if bar.bh > bar.bl else 0.0


def close_location(bar: Bar, side: str) -> float:
    if bar.bh <= bar.bl:
        return 0.0
    return (bar.bc - bar.bl) / (bar.bh - bar.bl) if side == "BUY" else (bar.bh - bar.bc) / (bar.bh - bar.bl)


def choose(level: int, loose: float, base: float, strict: float) -> float:
    return (loose, base, strict)[level + 1]


def within_discovery(series: Series, i: int) -> bool:
    return 0 <= i < len(series.bars) and DISCOVERY_START <= series.bars[i].dt < DISCOVERY_END


def past_index(series: Series, dt: datetime, hours: int) -> int | None:
    target = dt - timedelta(hours=hours)
    position = bisect.bisect_right(series.times, target) - 1
    return position if position >= 0 else None


def normalized_clock_return(series: Series, i: int, hours: int) -> float | None:
    if not series.atr[i] or series.atr[i] <= 0:
        return None
    old_i = past_index(series, series.bars[i].dt, hours)
    if old_i is None:
        return None
    return (series.bars[i].bc - series.bars[old_i].bc) / series.atr[i]


def detect_local(candidate_id: str, series: Series, level: int = 0) -> list[Signal]:
    output: list[Signal] = []
    bars = series.bars
    variant = ("loose", "base", "strict")[level + 1]
    start = 260
    seen_session: set[tuple[datetime.date, str]] = set()
    for i in range(start, len(bars)):
        if not within_discovery(series, i) or not series.atr[i] or series.atr[i] <= 0:
            continue
        bar, atr = bars[i], series.atr[i]
        side: str | None = None
        if candidate_id == "STRAT-PA-101":
            comp = max(x.bh for x in bars[i-6:i]) - min(x.bl for x in bars[i-6:i])
            comp_max = choose(level, 1.20, 1.00, 0.80)
            break_min = choose(level, 0.05, 0.10, 0.15)
            body_min = choose(level, 0.50, 0.60, 0.70)
            old_h, old_l = max(x.bh for x in bars[i-20:i]), min(x.bl for x in bars[i-20:i])
            if comp <= comp_max * atr and body_fraction(bar) >= body_min:
                if bar.bc >= old_h + break_min * atr and close_location(bar, "BUY") >= 0.80:
                    side = "BUY"
                elif bar.bc <= old_l - break_min * atr and close_location(bar, "SELL") >= 0.80:
                    side = "SELL"
        elif candidate_id == "STRAT-PA-102":
            lookback = int(choose(level, 5, 7, 9))
            break_min = choose(level, 0.00, 0.05, 0.10)
            body_min = choose(level, 0.40, 0.50, 0.60)
            inside = bars[i-1].bh <= bars[i-2].bh and bars[i-1].bl >= bars[i-2].bl
            nr = (bars[i-1].bh-bars[i-1].bl) <= min(x.bh-x.bl for x in bars[i-lookback:i])
            if inside and nr and body_fraction(bar) >= body_min:
                if bar.bc >= max(bars[i-1].bh, bars[i-2].bh)+break_min*atr and close_location(bar,"BUY")>=.75:
                    side="BUY"
                elif bar.bc <= min(bars[i-1].bl,bars[i-2].bl)-break_min*atr and close_location(bar,"SELL")>=.75:
                    side="SELL"
        elif candidate_id == "STRAT-PA-103":
            sep=choose(level,.15,.25,.35); slope=choose(level,.05,.10,.15); trigger=choose(level,0,.05,.10)
            if series.ema20[i-1]-series.ema50[i-1]>=sep*atr and series.ema20[i-1]-series.ema20[i-6]>=slope*atr:
                pull=bars[i-1].bl<=series.ema20[i-1] and bars[i-1].bc>=series.ema20[i-1]-.25*atr
                if pull and bar.bc>=bars[i-1].bh+trigger*atr and bar.bc>series.ema20[i] and bar.bc>bar.bo and body_fraction(bar)>=.40:
                    side="BUY"
            elif series.ema20[i-1]-series.ema50[i-1]<=-sep*atr and series.ema20[i-1]-series.ema20[i-6]<=-slope*atr:
                pull=bars[i-1].bh>=series.ema20[i-1] and bars[i-1].bc<=series.ema20[i-1]+.25*atr
                if pull and bar.bc<=bars[i-1].bl-trigger*atr and bar.bc<series.ema20[i] and bar.bc<bar.bo and body_fraction(bar)>=.40:
                    side="SELL"
        elif candidate_id == "STRAT-PA-104":
            move=choose(level,.75,1.0,1.25); body_min=choose(level,.25,.35,.45); loc=choose(level,.65,.75,.85)
            up=bars[i-2].bc<bars[i-1].bc<bar.bc; down=bars[i-2].bc>bars[i-1].bc>bar.bc
            bodies=all(body_fraction(x)>=body_min for x in bars[i-2:i+1])
            if bodies and abs(bar.bc-bars[i-3].bc)>=move*atr:
                if up and bar.bc>=bars[i-1].bh and close_location(bar,"BUY")>=loc: side="BUY"
                elif down and bar.bc<=bars[i-1].bl and close_location(bar,"SELL")>=loc: side="SELL"
        elif candidate_id == "STRAT-PA-105":
            if series.timeframe == "H4":
                continue
            range_end=int(choose(level,7,6,5)); signal_end=int(choose(level,11,10,9)); break_min=choose(level,.10,.15,.20)
            close_dt=bar.dt+(timedelta(minutes=15) if series.timeframe=="M15" else timedelta(hours=1))
            if not (range_end < close_dt.hour <= signal_end):
                continue
            day_window = 96 if series.timeframe == "M15" else 24
            same_day=[x for x in bars[max(0,i-day_window):i] if x.dt.date()==bar.dt.date() and x.dt.hour<range_end]
            if not same_day: continue
            old_h,old_l=max(x.bh for x in same_day),min(x.bl for x in same_day)
            if bar.bc>=old_h+break_min*atr and close_location(bar,"BUY")>=.75: side="BUY"
            elif bar.bc<=old_l-break_min*atr and close_location(bar,"SELL")>=.75: side="SELL"
            if side and (bar.dt.date(),side) in seen_session: side=None
            if side: seen_session.add((bar.dt.date(),side))
        elif candidate_id == "STRAT-VV-101":
            vr=choose(level,1.60,2.00,2.40); rr=choose(level,1.25,1.50,1.75); bf=choose(level,.50,.60,.70)
            if series.volume_ratio[i] is not None and series.volume_ratio[i]>=vr and bar.bh-bar.bl>=rr*atr and body_fraction(bar)>=bf:
                side="BUY" if bar.bc>bar.bo and close_location(bar,"BUY")>=.80 else ("SELL" if bar.bc<bar.bo and close_location(bar,"SELL")>=.80 else None)
        elif candidate_id == "STRAT-VV-102":
            quiet=series.quiet_q20[i]; quiet_bars=int(choose(level,6,8,10)); release=choose(level,1.10,1.30,1.50)
            if quiet is not None and statistics.median(series.tr[i-quiet_bars:i])<=quiet and bar.bh-bar.bl>=release*atr and body_fraction(bar)>=.55:
                side="BUY" if bar.bc>bar.bo and close_location(bar,"BUY")>=.75 else ("SELL" if bar.bc<bar.bo and close_location(bar,"SELL")>=.75 else None)
        elif candidate_id == "STRAT-VV-103":
            rr=choose(level,2.0,2.5,3.0); vr=choose(level,1.5,1.8,2.1); wick=choose(level,.35,.45,.55); rng=bar.bh-bar.bl
            if series.volume_ratio[i] is not None and rng>=rr*atr and series.volume_ratio[i]>=vr and rng>0:
                lower=min(bar.bo,bar.bc)-bar.bl; upper=bar.bh-max(bar.bo,bar.bc); prior=bars[i-1].bc-bars[i-4].bc
                if prior<=-atr and lower>=wick*rng and close_location(bar,"BUY")>=.65: side="BUY"
                elif prior>=atr and upper>=wick*rng and close_location(bar,"SELL")>=.65: side="SELL"
        elif candidate_id == "STRAT-VV-104":
            rr=choose(level,1.25,1.50,1.75); vmax=choose(level,.80,.70,.60); bf=choose(level,.40,.50,.60)
            if series.volume_ratio[i] is not None and bar.bh-bar.bl>=rr*atr and series.volume_ratio[i]<=vmax and body_fraction(bar)>=bf:
                if bar.bc>bar.bo and close_location(bar,"BUY")>=.70: side="SELL"
                elif bar.bc<bar.bo and close_location(bar,"SELL")>=.70: side="BUY"
        elif candidate_id == "STRAT-VV-105":
            onset=choose(level,1.30,1.50,1.70); prior_max=choose(level,1.30,1.20,1.10); move=choose(level,.60,.80,1.0)
            rv,base=series.rv12[i],series.rv_baseline[i]
            prior_rv,prior_base=series.rv12[i-1],series.rv_baseline[i-1]
            if rv and base and prior_rv and prior_base and rv>=onset*base and prior_rv<=prior_max*prior_base:
                delta=bar.bc-bars[i-6].bc
                if abs(delta)>=move*atr: side="BUY" if delta>0 else "SELL"
        if side:
            output.append(Signal(candidate_id,series.symbol,series.timeframe,i,side,variant))
    return output


def synchronized(series_by_symbol: dict[str, Series], symbols: tuple[str, ...], dt: datetime) -> list[tuple[Series, int]] | None:
    rows=[]
    for symbol in symbols:
        series=series_by_symbol.get(symbol); i=series.index.get(dt) if series else None
        if series is None or i is None or not series.atr[i]: return None
        rows.append((series,i))
    return rows


def detect_cross(candidate_id: str, target: Series, all_series: dict[str, Series], level: int = 0) -> list[Signal]:
    output=[]; variant=("loose","base","strict")[level+1]
    for i in range(260,len(target.bars)):
        if not within_discovery(target,i) or not target.atr[i]: continue
        dt=target.bars[i].dt; side=None
        if candidate_id in ("STRAT-MR-101","STRAT-MR-102"):
            symbols=USD_SET if candidate_id.endswith("101") else JPY_SET
            if target.symbol not in symbols: continue
            rows=synchronized(all_series,symbols,dt)
            if not rows: continue
            confirm=int(choose(level,2,3,4)); basket_min=choose(level,.60,.80,1.0); target_min=choose(level,.30,.50,.70)
            values=[]
            for series,j in rows:
                if j<6: values=[]; break
                value=(series.bars[j].bc-series.bars[j-6].bc)/series.atr[j]
                if candidate_id.endswith("101") and series.symbol in ("AUDUSD","EURUSD","GBPUSD"): value=-value
                values.append(value)
            if not values: continue
            positive=sum(x>0 for x in values); negative=sum(x<0 for x in values)
            sign=1 if positive>=confirm else (-1 if negative>=confirm else 0)
            oriented=(target.bars[i].bc-target.bars[i-6].bc)/target.atr[i]
            if candidate_id.endswith("101") and target.symbol in ("AUDUSD","EURUSD","GBPUSD"): oriented=-oriented
            if sign and statistics.median(abs(x) for x in values)>=basket_min and oriented*sign>=target_min:
                trade_sign=sign
                if candidate_id.endswith("101") and target.symbol in ("AUDUSD","EURUSD","GBPUSD"): trade_sign=-sign
                if trade_sign>0 and target.bars[i].bc>=max(x.bh for x in target.bars[i-6:i]): side="BUY"
                elif trade_sign<0 and target.bars[i].bc<=min(x.bl for x in target.bars[i-6:i]): side="SELL"
        elif candidate_id=="STRAT-MR-103":
            if target.symbol not in METALS: continue
            rows=synchronized(all_series,METALS,dt)
            if not rows: continue
            hours=int(choose(level,8,12,16)); threshold=choose(level,.50,.75,1.0); look=int(choose(level,4,6,8))
            values=[normalized_clock_return(s,j,hours) for s,j in rows]
            if any(x is None for x in values): continue
            sign=1 if all(x>=threshold for x in values) else (-1 if all(x<=-threshold for x in values) else 0)
            if sign>0 and target.bars[i].bc>=max(x.bh for x in target.bars[i-look:i]): side="BUY"
            elif sign<0 and target.bars[i].bc<=min(x.bl for x in target.bars[i-look:i]): side="SELL"
        elif candidate_id=="STRAT-MR-104":
            if target.symbol not in ENERGY: continue
            rows=synchronized(all_series,ENERGY,dt)
            if not rows: continue
            hours=int(choose(level,18,24,30)); zmin=choose(level,1.5,2.0,2.5); hist=int(choose(level,80,120,160))
            spreads=[]
            for back in range(hist,0,-1):
                past_dt=dt-timedelta(hours=back*(.25 if target.timeframe=="M15" else (1 if target.timeframe=="H1" else 4)))
                past_rows=synchronized(all_series,ENERGY,past_dt)
                if not past_rows: continue
                vals=[normalized_clock_return(s,j,hours) for s,j in past_rows]
                if all(x is not None for x in vals): spreads.append(vals[0]-vals[1])
            current=[normalized_clock_return(s,j,hours) for s,j in rows]
            if len(spreads)<max(40,hist//2) or any(x is None for x in current): continue
            sd=statistics.stdev(spreads)
            if sd<=0: continue
            z=((current[0]-current[1])-statistics.mean(spreads))/sd
            if z>=zmin: side="SELL" if target.symbol=="BRENTCMDUSD" else "BUY"
            elif z<=-zmin: side="BUY" if target.symbol=="BRENTCMDUSD" else "SELL"
        elif candidate_id=="STRAT-MR-105":
            if target.symbol not in COMMODITIES: continue
            rows=synchronized(all_series,COMMODITIES,dt)
            if not rows: continue
            confirm=int(choose(level,2,3,4)); basket_min=choose(level,.40,.60,.80); target_min=choose(level,.20,.40,.60)
            values=[normalized_clock_return(s,j,12) for s,j in rows]
            if any(x is None for x in values): continue
            positive=sum(x>0 for x in values); negative=sum(x<0 for x in values)
            sign=1 if positive>=confirm else (-1 if negative>=confirm else 0)
            target_value=normalized_clock_return(target,i,12)
            if sign and statistics.median(abs(x) for x in values)>=basket_min and target_value*sign>=target_min:
                if sign>0 and close_location(target.bars[i],"BUY")>=.70: side="BUY"
                elif sign<0 and close_location(target.bars[i],"SELL")>=.70: side="SELL"
        if side: output.append(Signal(candidate_id,target.symbol,target.timeframe,i,side,variant))
    return output


def exit_index(series: Series, entry_i: int, key: str) -> int | None:
    if key.startswith("bar_"):
        position=entry_i+int(key.split("_")[1])
    else:
        hours=int(key.split("_")[1][:-1]); target=series.bars[entry_i].dt+timedelta(hours=hours)
        position=bisect.bisect_left(series.times,target)
    if position>=len(series.bars) or series.bars[position].dt>=DISCOVERY_END: return None
    return position


def outcome(series: Series, signal: Signal) -> dict[str, dict[str, float]] | None:
    entry_i=signal.i+1
    if entry_i>=len(series.bars) or series.bars[entry_i].dt>=DISCOVERY_END or not series.atr[signal.i]: return None
    scale=series.atr[signal.i]; entry=series.bars[entry_i].ao if signal.side=="BUY" else series.bars[entry_i].bo
    result={}
    keys=[f"bar_{h}" for h in BAR_HORIZONS]+[f"clock_{h}h" for h in CLOCK_HORIZONS]
    for key in keys:
        ex=exit_index(series,entry_i,key)
        if ex is None: continue
        # Exit occurs at ex Open, so ex High/Low is not yet observable and must not enter MFE/MAE.
        path=series.bars[entry_i:ex]
        if not path:
            continue
        if signal.side=="BUY":
            ret=(series.bars[ex].bo-entry)/scale; mfe=(max(x.bh for x in path)-entry)/scale; mae=(min(x.bl for x in path)-entry)/scale
        else:
            ret=(entry-series.bars[ex].ao)/scale; mfe=(entry-min(x.al for x in path))/scale; mae=(entry-max(x.ah for x in path))/scale
        result[key]={"return":ret,"mfe":mfe,"mae":mae}
    return result if PRIMARY in result else None


def control_pairs(signals: list[Signal], series_map: dict[tuple[str,str],Series]) -> list[dict]:
    records=[]; grouped=defaultdict(list)
    for signal in signals: grouped[(signal.candidate_id,signal.symbol,signal.timeframe)].append(signal)
    for key,cell_signals in grouped.items():
        candidate_id,symbol,timeframe=key; series=series_map[(symbol,timeframe)]
        signal_indices={signal.i for signal in cell_signals}; reuse=defaultdict(int)
        pools=defaultdict(list)
        for i,bar in enumerate(series.bars):
            if not within_discovery(series,i) or i in signal_indices or None in (series.dec_atr[i],series.dec_trend[i],series.dec_spread[i],series.dec_volume[i]): continue
            pools[(bar.dt.year,bar.dt.hour//4)].append(i)
        for signal in cell_signals:
            sig_out=outcome(series,signal)
            if not sig_out: continue
            i=signal.i; bar=series.bars[i]; eligible=[]
            for j in pools[(bar.dt.year,bar.dt.hour//4)]:
                if abs((series.bars[j].dt-bar.dt).days)>90 or abs(j-i)<=24 or reuse[j]>=3: continue
                distance=sum(abs(a-b) for a,b in zip(
                    (series.dec_atr[i],series.dec_trend[i],series.dec_spread[i],series.dec_volume[i]),
                    (series.dec_atr[j],series.dec_trend[j],series.dec_spread[j],series.dec_volume[j]),
                ))
                tie=hashlib.sha256(f"{candidate_id}|{symbol}|{timeframe}|{i}|{j}|{SEED}".encode()).hexdigest()
                eligible.append((distance,tie,j))
            chosen=sorted(eligible)[:5]; controls=[]
            for _,__,j in chosen:
                hypothetical=Signal(candidate_id,symbol,timeframe,j,signal.side)
                value=outcome(series,hypothetical)
                if value: controls.append(value); reuse[j]+=1
            if len(controls)<3: continue
            control_primary=statistics.mean(x[PRIMARY]["return"] for x in controls)
            records.append({
                "candidate_id":candidate_id,"symbol":symbol,"timeframe":timeframe,"dt":bar.dt,"side":signal.side,
                "signal":sig_out,"control_primary":control_primary,
                "edge_primary":sig_out[PRIMARY]["return"]-control_primary,"controls":len(controls),
            })
    return records


def aggregate_records(rows: list[dict]) -> dict:
    if not rows: return {"matched_signals":0}
    horizon={}
    for key in [f"bar_{h}" for h in BAR_HORIZONS]+[f"clock_{h}h" for h in CLOCK_HORIZONS]:
        valid=[row["signal"][key] for row in rows if key in row["signal"]]
        horizon[key]={
            "n":len(valid),"mean_return_atr":statistics.mean(x["return"] for x in valid) if valid else None,
            "mean_mfe_atr":statistics.mean(x["mfe"] for x in valid) if valid else None,
            "mean_mae_atr":statistics.mean(x["mae"] for x in valid) if valid else None,
        }
    return {
        "matched_signals":len(rows),"mean_signal_return_atr":statistics.mean(x["signal"][PRIMARY]["return"] for x in rows),
        "mean_control_return_atr":statistics.mean(x["control_primary"] for x in rows),
        "mean_edge_atr":statistics.mean(x["edge_primary"] for x in rows),
        "median_edge_atr":statistics.median(x["edge_primary"] for x in rows),
        "positive_edge_rate":sum(x["edge_primary"]>0 for x in rows)/len(rows),"horizons":horizon,
    }


def cluster_stats(rows: list[dict], candidate_id: str) -> dict:
    groups=defaultdict(list)
    for row in rows: groups[(row["dt"].date().isoformat(),row["side"])].append(row["edge_primary"])
    episodes=[statistics.mean(values) for values in groups.values()]
    if not episodes: return {"unique_episodes":0,"episode_weighted_mean_edge_atr":None,"bootstrap_95ci":[None,None],"one_sided_p":None}
    rng=random.Random(int(hashlib.sha256(f"{candidate_id}|{SEED}".encode()).hexdigest()[:12],16)); means=[]
    for _ in range(10000): means.append(statistics.mean(rng.choice(episodes) for __ in episodes))
    means.sort(); ci=[means[int(.025*len(means))],means[int(.975*len(means))]]
    if len(episodes)>1 and statistics.stdev(episodes)>0:
        z=statistics.mean(episodes)/(statistics.stdev(episodes)/math.sqrt(len(episodes))); p=.5*math.erfc(z/math.sqrt(2))
    else: p=1.0
    return {"unique_episodes":len(episodes),"episode_weighted_mean_edge_atr":statistics.mean(episodes),"bootstrap_95ci":ci,"one_sided_p":p}


def episode_weighted_effect(rows: list[dict]) -> float | None:
    groups=defaultdict(list)
    for row in rows:
        groups[(row["dt"].date().isoformat(),row["side"])].append(row["edge_primary"])
    return statistics.mean(statistics.mean(values) for values in groups.values()) if groups else None


def bh_adjust(items: list[tuple[str,float]]) -> dict[str,float]:
    ordered=sorted(items,key=lambda x:x[1]); m=len(ordered); adjusted={}; running=1.0
    for rank in range(m,0,-1):
        candidate,p=ordered[rank-1]; running=min(running,p*m/rank); adjusted[candidate]=running
    return adjusted


def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--data-dir",type=Path,required=True); parser.add_argument("--base-timeframe",choices=("M15","H1"),required=True); parser.add_argument("--output-dir",type=Path,required=True)
    args=parser.parse_args(); args.output_dir.mkdir(parents=True,exist_ok=True)
    registry_path=Path(__file__).resolve().parents[1]/"spec"/"candidate_registry.json"
    registry=json.loads(registry_path.read_text(encoding="utf-8")); candidate_meta={x["strategy_id"]:x for x in registry["candidates"]}
    raw={symbol:load_pair(args.data_dir,symbol,args.base_timeframe) for symbol in ALL_SYMBOLS}
    series_map={}
    if args.base_timeframe=="M15":
        for symbol,bars in raw.items(): series_map[(symbol,"M15")]=build_series(symbol,"M15",bars)
    else:
        for symbol,bars in raw.items():
            series_map[(symbol,"H1")]=build_series(symbol,"H1",bars)
            series_map[(symbol,"H4")]=build_series(symbol,"H4",aggregate(bars,4))
    all_base_signals=[]; sensitivity={}; raw_counts={}
    local_ids=[f"STRAT-PA-{n}" for n in range(101,106)]+[f"STRAT-VV-{n}" for n in range(101,106)]
    cross_ids=[f"STRAT-MR-{n}" for n in range(101,106)]
    for candidate_id in local_ids+cross_ids:
        sensitivity[candidate_id]={}
        for level,variant in [(-1,"loose"),(0,"base"),(1,"strict")]:
            signals=[]
            for (symbol,timeframe),series in series_map.items():
                if timeframe not in candidate_meta[candidate_id]["timeframes"]: continue
                if candidate_id in local_ids: signals.extend(detect_local(candidate_id,series,level))
                else:
                    tf_context={sym:s for (sym,tf),s in series_map.items() if tf==timeframe}
                    signals.extend(detect_cross(candidate_id,series,tf_context,level))
            returns=[]
            for signal in signals:
                value=outcome(series_map[(signal.symbol,signal.timeframe)],signal)
                if value: returns.append(value[PRIMARY]["return"])
            sensitivity[candidate_id][variant]={"signals":len(returns),"raw_mean_return_atr":statistics.mean(returns) if returns else None}
            if level==0:
                all_base_signals.extend(signals); raw_counts[candidate_id]=len(returns)
    matched=control_pairs(all_base_signals,series_map); reports=[]; pvalues=[]
    for candidate_id,meta in candidate_meta.items():
        rows=[x for x in matched if x["candidate_id"]==candidate_id]; overall=aggregate_records(rows); clusters=cluster_stats(rows,candidate_id)
        pvalues.append((candidate_id,clusters["one_sided_p"] if clusters["one_sided_p"] is not None else 1.0))
        by_year={str(year):aggregate_records([x for x in rows if x["dt"].year==year]) for year in sorted({x["dt"].year for x in rows})}
        by_instrument={symbol:aggregate_records([x for x in rows if x["symbol"]==symbol]) for symbol in sorted({x["symbol"] for x in rows})}
        by_timeframe={tf:aggregate_records([x for x in rows if x["timeframe"]==tf]) for tf in sorted({x["timeframe"] for x in rows})}
        base=sensitivity[candidate_id]["base"]["raw_mean_return_atr"]; signs=[]
        for variant in ("loose","base","strict"):
            value=sensitivity[candidate_id][variant]["raw_mean_return_atr"]
            signs.append(value is not None and base is not None and value*base>0)
        reports.append({
            "strategy_id":candidate_id,"family":meta["family"],"hypothesis":meta["hypothesis"],"entry_conditions":meta["entry_conditions"],
            "information_available_at_entry":registry["common_information_rule"],"targets":meta["targets"],"registered_timeframes":meta["timeframes"],
            "sample_size":{"raw_signals_with_primary_outcome":raw_counts.get(candidate_id,0),"matched_signals":overall.get("matched_signals",0),"unique_episodes":clusters["unique_episodes"]},
            "matched_control":"Same candidate/instrument/timeframe/split/hypothetical side/year/UTC4h; nearest prior-only ATR/trend/spread/volume deciles within ±90d; 5 requested, 3 minimum, reuse cap 3.",
            "future_return_mfe_mae":overall.get("horizons",{}),"primary_clock_12h":overall,"cluster_inference":clusters,
            "by_year":by_year,"by_instrument":by_instrument,"by_timeframe":by_timeframe,
            "parameter_sensitivity":{"registered_grid":meta["parameter_sensitivity"],"joint_loose_base_strict":sensitivity[candidate_id],"same_sign_ratio":sum(signs)/3},
            "weaknesses":meta["weaknesses"],"decision":"PENDING_FDR",
        })
    adjusted=bh_adjust(pvalues)
    for report in reports:
        cid=report["strategy_id"]; n=report["sample_size"]["unique_episodes"]
        ci=report["cluster_inference"]["bootstrap_95ci"]
        candidate_rows=[x for x in matched if x["candidate_id"]==cid]
        market_values=[episode_weighted_effect([x for x in candidate_rows if x["symbol"]==symbol]) for symbol in sorted({x["symbol"] for x in candidate_rows})]
        tf_values=[episode_weighted_effect([x for x in candidate_rows if x["timeframe"]==tf]) for tf in sorted({x["timeframe"] for x in candidate_rows})]
        market_values=[x for x in market_values if x is not None]; tf_values=[x for x in tf_values if x is not None]
        market_ratio=sum(x>0 for x in market_values)/len(market_values) if market_values else 0; tf_ratio=sum(x>0 for x in tf_values)/len(tf_values) if tf_values else 0
        report["cluster_inference"]["bh_fdr_adjusted_p"]=adjusted[cid]; sens=report["parameter_sensitivity"]["same_sign_ratio"]
        episode_edge=report["cluster_inference"]["episode_weighted_mean_edge_atr"] or 0
        report["primary_clock_12h"]["effect_note"]="mean_edge_atr is signal-weighted descriptive output; promotion uses episode_weighted_mean_edge_atr from cluster_inference."
        if n>=100 and episode_edge>=.05 and ci[0] is not None and ci[0]>0 and adjusted[cid]<=.10 and market_ratio>=.60 and tf_ratio>=.67 and sens>=.67:
            report["decision"]="DEVELOPMENT"
        elif n>=50 and episode_edge>0:
            report["decision"]="WATCH"
        else: report["decision"]="REJECT"
        report["decision_inputs"]={"positive_market_ratio":market_ratio,"positive_timeframe_ratio":tf_ratio,"sensitivity_same_sign_ratio":sens}
    ranked={}
    for family in ("PRICE_ACTION","VOLUME_VOLATILITY","MARKET_REGIME_CROSS_MARKET"):
        candidates=[x for x in reports if x["family"]==family]
        ranked[family]=[x["strategy_id"] for x in sorted(candidates,key=lambda x:x["cluster_inference"].get("episode_weighted_mean_edge_atr") if x["cluster_inference"].get("episode_weighted_mean_edge_atr") is not None else -999,reverse=True)]
    manifest={"base_timeframe":args.base_timeframe,"series":[{"symbol":s.symbol,"timeframe":s.timeframe,"rows":len(s.bars),"first":s.bars[0].dt.isoformat(),"last":s.bars[-1].dt.isoformat()} for s in series_map.values()]}
    output={"phase":"PHASE8_BLIND_DISCOVERY","evaluated_split":"DISCOVERY_ONLY","evaluated_period":[DISCOVERY_START.isoformat(),DISCOVERY_END.isoformat()],"development_oos_final_holdout_accessed":False,"signal_basis":"BID_OHLC_AND_BID_TICK_VOLUME","primary_horizon":"CLOCK_12H","ranked_top5_per_family":ranked,"candidates":reports,"data_manifest":manifest}
    (args.output_dir/f"phase8_{args.base_timeframe.lower()}_candidate_report.json").write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"base_timeframe":args.base_timeframe,"signals":len(all_base_signals),"matched":len(matched),"ranked":ranked},ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()
