#!/usr/bin/env python3
"""Candidate-independent calculations for unified FX/commodity backtests."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import hashlib
import math
import random
from statistics import fmean, median
from typing import Iterable, Sequence


@dataclass(frozen=True)
class Bar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None


@dataclass(frozen=True)
class QuoteBar:
    timestamp: datetime
    bid: Bar
    ask: Bar


@dataclass(frozen=True)
class Signal:
    strategy_id: str
    symbol: str
    direction: str
    signal_time: datetime
    entry_time: datetime
    execution_timeframe: str


@dataclass(frozen=True)
class Outcome:
    strategy_id: str
    symbol: str
    direction: str
    horizon: str
    entry_time: datetime
    exit_time: datetime
    entry_index: int
    exit_index: int
    entry_price: float
    exit_price: float
    r: float
    mfe_r: float
    mae_r: float


class CoreError(RuntimeError):
    pass


TIMEFRAME_STEPS = {
    "M1": timedelta(minutes=1),
    "M5": timedelta(minutes=5),
    "M15": timedelta(minutes=15),
    "M30": timedelta(minutes=30),
    "H1": timedelta(hours=1),
    "H4": timedelta(hours=4),
    "D1": timedelta(days=1),
}


def true_range(current: Bar, previous: Bar) -> float:
    return max(
        current.high - current.low,
        abs(current.high - previous.close),
        abs(current.low - previous.close),
    )


def atr_before(bars: Sequence[Bar], index: int, period: int, step: timedelta) -> float | None:
    """ATR ending at index-1. The entry bar at index is never used."""
    if period <= 0 or index < period + 1:
        return None
    start = index - period
    required = bars[start - 1:index]
    if len(required) != period + 1:
        return None
    if any(required[pos + 1].timestamp - required[pos].timestamp != step for pos in range(period)):
        return None
    values = [true_range(bars[pos], bars[pos - 1]) for pos in range(start, index)]
    value = sum(values) / period
    return value if math.isfinite(value) and value > 0 else None


def midpoint_series(quotes: Sequence[QuoteBar]) -> list[Bar]:
    output = []
    for quote in quotes:
        values = [
            (getattr(quote.bid, field) + getattr(quote.ask, field)) / 2.0
            for field in ("open", "high", "low", "close")
        ]
        bar = Bar(quote.timestamp, *values, None)
        if bar.low > min(bar.open, bar.close) or bar.high < max(bar.open, bar.close) or bar.low > bar.high:
            raise CoreError("midpoint OHLC geometry mismatch")
        output.append(bar)
    return output


def signal_identity(rows: Iterable[Signal]) -> str:
    payload = "".join(
        f"{row.strategy_id}\0{row.symbol}\0{row.direction}\0{row.signal_time.isoformat()}\0"
        f"{row.entry_time.isoformat()}\0{row.execution_timeframe}\n"
        for row in sorted(rows, key=lambda item: (
            item.strategy_id, item.entry_time, item.symbol, item.direction,
            item.signal_time, item.execution_timeframe,
        ))
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def collapse_connected(signals: Sequence[Signal], overlap_hours: int) -> list[Signal]:
    """Transitive half-open components; exactly overlap_hours is separate."""
    if overlap_hours <= 0:
        raise CoreError("episode overlap must be positive")
    identities = [
        (row.strategy_id, row.symbol, row.direction, row.signal_time, row.entry_time, row.execution_timeframe)
        for row in signals
    ]
    if len(identities) != len(set(identities)):
        raise CoreError("duplicate signal identity")
    grouped: dict[tuple[str, str, str], list[Signal]] = defaultdict(list)
    for row in signals:
        grouped[(row.strategy_id, row.symbol, row.direction)].append(row)
    output: list[Signal] = []
    duration = timedelta(hours=overlap_hours)
    for key in sorted(grouped):
        rows = sorted(grouped[key], key=lambda item: (
            item.entry_time, item.signal_time, item.execution_timeframe, item.symbol, item.direction,
        ))
        representative = rows[0]
        component_end = representative.entry_time + duration
        for row in rows[1:]:
            if row.entry_time >= component_end:
                output.append(representative)
                representative = row
                component_end = row.entry_time + duration
            else:
                component_end = max(component_end, row.entry_time + duration)
        output.append(representative)
    return sorted(output, key=lambda item: (
        item.entry_time, item.strategy_id, item.symbol, item.direction,
        item.signal_time, item.execution_timeframe,
    ))


def _horizon_exit_index(
    bars: Sequence[Bar], entry_index: int, horizon: str, timeframe: str,
    timestamp_index: dict[datetime, int] | None = None,
) -> int | None:
    if horizon.startswith("BAR_"):
        count = int(horizon.removeprefix("BAR_"))
        target = entry_index + count
        if target >= len(bars):
            return None
        step = TIMEFRAME_STEPS[timeframe]
        if bars[target].timestamp - bars[entry_index].timestamp != step * count:
            return None
        return target
    if horizon.startswith("CLOCK_") and horizon.endswith("H"):
        hours = int(horizon.removeprefix("CLOCK_").removesuffix("H"))
        target_time = bars[entry_index].timestamp + timedelta(hours=hours)
        mapping = timestamp_index if timestamp_index is not None else {
            row.timestamp: index for index, row in enumerate(bars)
        }
        target = mapping.get(target_time)
        if target is None:
            return None
        step = TIMEFRAME_STEPS[timeframe]
        duration = timedelta(hours=hours)
        if duration.total_seconds() % step.total_seconds():
            return None
        count = int(duration.total_seconds() // step.total_seconds())
        expected = [bars[entry_index].timestamp + step * offset for offset in range(count + 1)]
        if target - entry_index != count or [row.timestamp for row in bars[entry_index:target + 1]] != expected:
            return None
        return target
    raise CoreError(f"unknown horizon: {horizon}")


def evaluate_horizon(
    signal: Signal,
    quotes: Sequence[QuoteBar],
    midpoint: Sequence[Bar],
    horizon: str,
    atr_period: int,
    additional_commission_price: float = 0.0,
    slippage_price: float = 0.0,
    timestamp_index: dict[datetime, int] | None = None,
) -> Outcome | None:
    if len(quotes) != len(midpoint) or [q.timestamp for q in quotes] != [b.timestamp for b in midpoint]:
        raise CoreError("quote/midpoint identity mismatch")
    mapping = timestamp_index if timestamp_index is not None else {
        row.timestamp: index for index, row in enumerate(midpoint)
    }
    entry_index = mapping.get(signal.entry_time)
    if entry_index is None:
        return None
    exit_index = _horizon_exit_index(
        midpoint, entry_index, horizon, signal.execution_timeframe, mapping
    )
    if exit_index is None:
        return None
    step = TIMEFRAME_STEPS[signal.execution_timeframe]
    atr = atr_before(midpoint, entry_index, atr_period, step)
    if atr is None:
        return None
    entry_quote = quotes[entry_index]
    exit_quote = quotes[exit_index]
    path = quotes[entry_index:exit_index]
    costs = additional_commission_price + slippage_price
    if signal.direction == "BUY":
        entry_price = entry_quote.ask.open
        exit_price = exit_quote.bid.open
        terminal = exit_price - entry_price - costs
        favorable = max([exit_price - entry_price, *[row.bid.high - entry_price for row in path]])
        adverse = min([exit_price - entry_price, *[row.bid.low - entry_price for row in path]])
    elif signal.direction == "SELL":
        entry_price = entry_quote.bid.open
        exit_price = exit_quote.ask.open
        terminal = entry_price - exit_price - costs
        favorable = max([entry_price - exit_price, *[entry_price - row.ask.low for row in path]])
        adverse = min([entry_price - exit_price, *[entry_price - row.ask.high for row in path]])
    else:
        raise CoreError("direction must be BUY or SELL")
    values = (terminal / atr, max(0.0, favorable) / atr, max(0.0, -adverse) / atr)
    if not all(math.isfinite(value) for value in values):
        raise CoreError("non-finite outcome")
    return Outcome(
        signal.strategy_id, signal.symbol, signal.direction, horizon,
        signal.entry_time, exit_quote.timestamp, entry_index, exit_index,
        entry_price, exit_price, *values,
    )


def max_drawdown(values: Sequence[float]) -> float:
    cumulative = peak = drawdown = 0.0
    for value in values:
        cumulative += value
        peak = max(peak, cumulative)
        drawdown = max(drawdown, peak - cumulative)
    return drawdown


def rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 10)


def metrics(rows: Sequence[Outcome]) -> dict:
    ordered = sorted(rows, key=lambda row: (row.exit_time, row.entry_time, row.symbol, row.direction))
    values = [row.r for row in ordered]
    if not values:
        return {
            "trade_count": 0, "mean_r": None, "median_r": None, "sum_r": 0.0,
            "win_rate": None, "profit_factor": None, "max_drawdown_r": 0.0,
            "mean_mfe_r": None, "mean_mae_r": None,
        }
    gross_profit = sum(value for value in values if value > 0)
    gross_loss = -sum(value for value in values if value < 0)
    profit_factor = None if gross_loss == 0 and gross_profit > 0 else (
        0.0 if gross_loss == 0 else gross_profit / gross_loss
    )
    return {
        "trade_count": len(values),
        "mean_r": rounded(fmean(values)),
        "median_r": rounded(median(values)),
        "sum_r": rounded(sum(values)),
        "win_rate": rounded(sum(value > 0 for value in values) / len(values)),
        "profit_factor": rounded(profit_factor),
        "max_drawdown_r": rounded(max_drawdown(values)),
        "mean_mfe_r": rounded(fmean(row.mfe_r for row in ordered)),
        "mean_mae_r": rounded(fmean(row.mae_r for row in ordered)),
    }


def clustered_lower_bound(
    rows: Sequence[Outcome], resamples: int, alpha: float, seed: int
) -> float | None:
    groups: dict[date, list[float]] = defaultdict(list)
    for row in rows:
        groups[row.entry_time.date()].append(row.r)
    clusters = list(groups.values())
    if not clusters:
        return None
    if resamples <= 0 or not 0 < alpha < 1:
        raise CoreError("invalid bootstrap settings")
    rng = random.Random(seed)
    estimates = []
    for _ in range(resamples):
        samples = [clusters[rng.randrange(len(clusters))] for _ in clusters]
        estimates.append(sum(sum(sample) for sample in samples) / sum(len(sample) for sample in samples))
    estimates.sort()
    index = max(0, min(len(estimates) - 1, math.ceil(alpha * len(estimates)) - 1))
    return rounded(estimates[index])
