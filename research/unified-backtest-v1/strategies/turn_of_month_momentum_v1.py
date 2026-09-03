"""EXP-P9-MTF-323-V1: leak-free turn-of-month momentum signal only."""


def generate_signals(api, strategy):
    params = strategy["parameters"]
    decision_hour = params["decision_hour_utc"]
    entry_hour = params["entry_hour_utc"]
    completed_count = params["completed_d1_count"]
    atr_period = params["atr_period"]
    threshold = params["minimum_move_atr"]
    output = []
    for symbol in api.symbols(strategy["required_timeframes"]):
        h1 = api.series(symbol, "H1")
        d1 = api.series(symbol, "D1")
        h1_times = {row.timestamp for row in h1}
        dates_by_month = {}
        for row in h1:
            month = (row.timestamp.year, row.timestamp.month)
            dates_by_month.setdefault(month, set()).add((row.timestamp.year, row.timestamp.month, row.timestamp.day))
        for month in sorted(dates_by_month):
            decision_time = None
            for year, month_number, day in sorted(dates_by_month[month]):
                midnight = api.make_time(year, month_number, day, 0)
                completed_hours = [api.add_time(midnight, hours=hour) for hour in range(decision_hour)]
                if any(stamp in h1_times for stamp in completed_hours):
                    decision_time = api.add_time(midnight, hours=decision_hour)
                    break
            if decision_time is None:
                continue
            # The first eligible date is consumed even if 08:00/09:00 is missing: no later roll.
            entry_time = api.add_time(decision_time, hours=1)
            if entry_hour != decision_hour + 1 or entry_time not in h1_times:
                continue
            completed = [bar for bar in d1 if api.add_time(bar.timestamp, days=1) <= decision_time]
            if len(completed) < completed_count:
                continue
            window = completed[-completed_count:]
            if len(window) < atr_period + 1:
                continue
            atr_rows = window[-(atr_period + 1):]
            ranges = []
            for index in range(1, len(atr_rows)):
                current = atr_rows[index]
                previous = atr_rows[index - 1]
                ranges.append(max(
                    current.high - current.low,
                    abs(current.high - previous.close),
                    abs(current.low - previous.close),
                ))
            atr = sum(ranges) / atr_period
            move = window[-1].close - window[0].close
            if atr <= 0 or move == 0 or abs(move) < threshold * atr:
                continue
            direction = "BUY" if move > 0 else "SELL"
            output.append(api.signal(strategy["strategy_id"], symbol, direction, decision_time, entry_time))
    return output
