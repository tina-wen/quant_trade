from datetime import datetime

"""
根据信号时序和当前持仓生成signal2trade
"""


def signal2trade(signal, prices, code, stop_loss, shares=1):
    # Extract times and signals from signal parameter (expected to be dict or similar structure)
    # Initialize required variables
    cols = ["time", "operation", "code", "price", "direction", "stop_loss"]
    trade_orders = []
    prev_s = 0
    times = signal.index if hasattr(signal, "index") else []
    signals = signal.values if hasattr(signal, "values") else signal

    for time, s, price in zip(times, signals, prices):
        if s != s:
            continue
        time = datetime.strptime(time, "%Y-%m-%d")
        # 之前无信号
        if not len(trade_orders):
            # signal为0时
            if not s:
                continue
            # 开仓
            direction = "long" if s == 1 else "short"
            trade_info = dict(zip(cols, [time, "open", code, price, direction, stop_loss]))
            for _ in range(shares):
                trade_orders.append(trade_info)
        # 之前有信号
        else:
            # 信号没变
            if s == prev_s:
                continue
            # 信号变为多
            if s == 1:
                # 之前信号为空，先买平
                if prev_s:
                    trade_info = dict(zip(cols, [time, "close", code, price, "long", None]))
                    for _ in range(shares):
                        trade_orders.append(trade_info)
                # 买开
                trade_info = dict(zip(cols, [time, "open", code, price, "long", stop_loss]))
                for _ in range(shares):
                    trade_orders.append(trade_info)
            # 信号变为空
            elif s == -1:
                # 之前信号为多，先卖平
                if prev_s:
                    trade_info = dict(zip(cols, [time, "close", code, price, "short", None]))
                    for _ in range(shares):
                        trade_orders.append(trade_info)
                # 卖开
                trade_info = dict(zip(cols, [time, "open", code, price, "short", stop_loss]))
                for _ in range(shares):
                    trade_orders.append(trade_info)
            # 信号由多头变为空仓，卖平
            elif prev_s == 1:
                trade_info = dict(zip(cols, [time, "close", code, price, "short", None]))
                for _ in range(shares):
                    trade_orders.append(trade_info)
            # 信号由空头变为空仓，买平
            else:
                trade_info = dict(zip(cols, [time, "close", code, price, "long", stop_loss]))
                for _ in range(shares):
                    trade_orders.append(trade_info)
        prev_s = s
    return trade_orders if trade_orders else []
