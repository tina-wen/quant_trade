from datetime import datetime, timedelta

import holidays
import pandas as pd

from get_data import DataQuery, normalize_interval, resolve_trade_date

from .account_statistics import acc_stats


def get_trade_day(start_date, end_date):
    tradeday_list = []
    current_date = start_date
    cn_holidays = holidays.China(years=list(range(start_date.year, end_date.year + 1)))
    while current_date <= end_date:
        if current_date.weekday() not in (5, 6) and current_date not in cn_holidays:
            tradeday_list.append(current_date)
        current_date += timedelta(days=1)
    return tradeday_list


def signal2dir(signal):
    sig2dir = {1.0: "long", -1.0: "short", 0.0: None}
    return sig2dir[signal]


class TradeOrder:
    """Trade order container for simulation input."""

    def __init__(self, signal, prices, code: str, interval: str, stop_loss, n_shares):
        self.signal = signal.tolist()
        time = signal.index.tolist()
        # self.time = [datetime.strptime(t,'%Y-%m-%d') for t in time]
        self.time = time
        self.prices = prices.tolist()
        self.code = code
        self.interval = normalize_interval(interval)
        self.stop_loss = stop_loss
        self.shares = n_shares


class trade_simulation:
    def __init__(
        self,
        account: acc_stats,
    ):
        self.account = account

    def backtest(self, trade_order: TradeOrder, margin_call, data_query: DataQuery):
        daily_balances = {}

        bar_times = getattr(data_query, "bar_times", getattr(data_query, "trade_days", []))
        if not bar_times:
            return daily_balances

        trade_dates = getattr(
            data_query,
            "trade_dates",
            [
                resolve_trade_date(bar_time, trade_order.code, data_query.exchange)
                for bar_time in bar_times
            ],
        )

        index_signal = 0
        stop_loss_triggered = False  # 发生过止损，限制同向再入场
        origin_dir = None  # 触发止损时的持仓方向

        for bar_index, bar_time in enumerate(bar_times):
            bar_trade_date = trade_dates[bar_index]
            open_price, high_price, low_price, close_price = (
                data_query.open_price[bar_index],
                data_query.high_price[bar_index],
                data_query.low_price[bar_index],
                data_query.close_price[bar_index],
            )

            # 每根bar都检查止损；do_stop_loss无持仓时直接返回(False, None)
            sl_fired, sl_dir = self.account.do_stop_loss(
                bar_time,
                trade_order.code,
                open_price,
                high_price,
                low_price,
                close_price,
            )
            if sl_fired:
                stop_loss_triggered = True
                origin_dir = sl_dir

            while index_signal < len(trade_order.signal):
                cur_time, signal, price = (
                    trade_order.time[index_signal],
                    trade_order.signal[index_signal],
                    trade_order.prices[index_signal],
                )
                cur_trade_date = resolve_trade_date(cur_time, trade_order.code, data_query.exchange)

                if cur_trade_date > bar_trade_date or cur_time > bar_time:
                    break

                if pd.isna(signal):
                    index_signal += 1
                    continue

                n, direction = self.account.get_position_by_code(trade_order.code)
                if (
                    direction is None
                    and signal
                    and (not stop_loss_triggered or signal2dir(signal) != origin_dir)
                ):  # 无持仓且有交易信号，且非止损后同向开仓，才执行开仓
                    for _ in range(trade_order.shares):
                        res = self.account.open_pos(
                            trade_order.code,
                            price,
                            signal2dir(signal),
                            trade_order.stop_loss,
                            cur_time,
                        )
                        if not res:  # 资金不足，停止本次开仓尝试，不修改止损状态
                            break
                    else:
                        stop_loss_triggered = False
                elif direction != signal2dir(
                    signal
                ):  # 有持仓但交易信号反向，执行平仓后再开新仓（如果有信号）
                    close_dir = "long" if direction == "short" else "short"
                    for _ in range(n):
                        target_trade = self.account.get_target_close_trade(
                            trade_order.code, close_dir
                        )
                        self.account.close_pos(
                            trade_order.code, price, close_dir, target_trade, cur_time
                        )
                    if signal and (not stop_loss_triggered or signal2dir(signal) != origin_dir):
                        for _ in range(trade_order.shares):
                            res = self.account.open_pos(
                                trade_order.code, price, close_dir, trade_order.stop_loss, cur_time
                            )
                            if not res:  # 资金不足，停止本次开仓尝试，不修改止损状态
                                break
                        else:
                            stop_loss_triggered = False
                index_signal += 1

            is_last_bar_of_trade_day = (
                bar_index == len(bar_times) - 1 or trade_dates[bar_index + 1] != bar_trade_date
            )
            if is_last_bar_of_trade_day:
                settle_dt = datetime.combine(bar_trade_date, datetime.min.time())
                self.account.MTM(margin_call, settle_dt)
                daily_balances[settle_dt] = {"balance": self.account.balance}

        return daily_balances

    def calc_performances(
        self,
        trade_order: TradeOrder,
        margin_call: float,
        data_query: DataQuery,
        n_tradeday=250,
        risk_free_rate=0.04,
    ):
        daily_balances = self.backtest(trade_order, margin_call, data_query)

        pnl = pd.DataFrame.from_dict(daily_balances, orient="index")
        pnl.sort_index(inplace=True)
        # Compute annual return, Sharpe ratio, and max drawdown.
        pnl["daily_profit"] = pnl["balance"].diff()

        self.pnl = pnl

        annual_ret = pnl["daily_profit"].mean() / self.account.init_bal * n_tradeday
        annual_vol = (pnl["daily_profit"] / self.account.init_bal).std() * n_tradeday**0.5
        sharpe_ratio = (annual_ret - risk_free_rate) / annual_vol
        max_drawdown = max(1 - pnl["balance"] / pnl["balance"].cummax())

        # Compute win rate and profit/loss ratio from closed trades.
        n_trades, n_win_trades = 0, 0
        gain, loss = 0, 0
        for code, trades in self.account.close_trade_items.items():
            n_trades += len(trades)
            for trade in trades:
                profit = trade.get_profits()
                if profit > 0:
                    n_win_trades += 1
                    gain += profit
                elif profit < 0:
                    loss -= profit
        assert n_trades > 0, "没有完成过任何交易，无法计算胜率和盈亏比"
        winning_rat, profit2loss = n_win_trades / n_trades, gain / loss
        perf_msg = (
            f"用户{self.account.usr}本次模拟的年化收益：{annual_ret:.2%}，"
            f"夏普：{round(sharpe_ratio, 2)}，最大回撤：{max_drawdown:.2%}，"
            f"胜率：{winning_rat:.2%}，盈亏比：{round(profit2loss, 2)}"
        )
        print(perf_msg)
        self.perf_dict = {
            "年化收益": f"{annual_ret:.2%}",
            "夏普比率": round(sharpe_ratio, 2),
            "最大回撤": f"{max_drawdown:.2%}",
            "胜率": f"{winning_rat:.2%}",
            "盈亏比": round(profit2loss, 2),
        }
        if n_trades < 10:
            self.perf_dict["警示信息"] = "成交单数过少，胜率/盈亏比可能不准确"
