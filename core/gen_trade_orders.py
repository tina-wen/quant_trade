from datetime import datetime

"""Generate trade orders from a signal time series."""


def signal2trade(signal, prices, code, stop_loss, shares=1):
    cols = ["time", "operation", "code", "price", "direction", "stop_loss"]
    trade_orders = []
    prev_s = 0
    times = signal.index if hasattr(signal, "index") else []
    signals = signal.values if hasattr(signal, "values") else signal

    for time, s, price in zip(times, signals, prices):
        if s != s:
            continue
        time = datetime.strptime(time, "%Y-%m-%d")
        if not len(trade_orders):
            if not s:
                continue
            direction = "long" if s == 1 else "short"
            trade_info = dict(zip(cols, [time, "open", code, price, direction, stop_loss]))
            for _ in range(shares):
                trade_orders.append(trade_info)
        else:
            if s == prev_s:
                continue
            if s == 1:
                if prev_s:
                    trade_info = dict(zip(cols, [time, "close", code, price, "long", None]))
                    for _ in range(shares):
                        trade_orders.append(trade_info)
                trade_info = dict(zip(cols, [time, "open", code, price, "long", stop_loss]))
                for _ in range(shares):
                    trade_orders.append(trade_info)
            elif s == -1:
                if prev_s:
                    trade_info = dict(zip(cols, [time, "close", code, price, "short", None]))
                    for _ in range(shares):
                        trade_orders.append(trade_info)
                trade_info = dict(zip(cols, [time, "open", code, price, "short", stop_loss]))
                for _ in range(shares):
                    trade_orders.append(trade_info)
            elif prev_s == 1:
                trade_info = dict(zip(cols, [time, "close", code, price, "short", None]))
                for _ in range(shares):
                    trade_orders.append(trade_info)
            else:
                trade_info = dict(zip(cols, [time, "close", code, price, "long", stop_loss]))
                for _ in range(shares):
                    trade_orders.append(trade_info)
        prev_s = s
    return trade_orders if trade_orders else []
