"""EXP-P9-MTF-322-V1: H1 same-sign exhaustion signal only."""


def generate_signals(api, strategy):
    params = strategy["parameters"]
    run_length = params["run_length"]
    atr_period = params["atr_period"]
    threshold = params["minimum_move_atr"]
    output = []
    for symbol in api.symbols(strategy["required_timeframes"]):
        bars = api.series(symbol, "H1")
        by_time = {row.timestamp: index for index, row in enumerate(bars)}
        for index in range(max(run_length + 1, atr_period + 1), len(bars) - 1):
            current = bars[index]
            entry_time = api.add_time(current.timestamp, hours=1)
            first_required = current.timestamp
            for lookback in range(max(run_length + 1, atr_period + 1)):
                first_required = api.add_time(first_required, hours=-1)
            required_count = max(run_length + 1, atr_period + 1) + 2
            exact_grid = [api.add_time(first_required, hours=offset) for offset in range(required_count)]
            if [by_time.get(stamp) for stamp in exact_grid] != list(range(index - required_count + 2, index + 2)):
                continue
            changes = [
                bars[right].close - bars[right - 1].close
                for right in range(index - run_length + 1, index + 1)
            ]
            positive = all(value > 0 for value in changes)
            negative = all(value < 0 for value in changes)
            if not (positive or negative):
                continue
            previous = bars[index - run_length].close - bars[index - run_length - 1].close
            if (positive and previous > 0) or (negative and previous < 0):
                continue
            atr = api.atr_before(symbol, "H1", index, atr_period)
            if atr is None or abs(bars[index].close - bars[index - run_length].close) < threshold * atr:
                continue
            direction = "SELL" if positive else "BUY"
            # current close is available at entry_time, never at current bar open.
            output.append(api.signal(strategy["strategy_id"], symbol, direction, entry_time, entry_time))
    return output
