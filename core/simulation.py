from datetime import timedelta

import holidays
import pandas as pd

from get_data import DataQuery, freq_dict

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
        if isinstance(interval, str):
            self.interval = freq_dict.get(interval, interval)
        else:
            self.interval = interval
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

        no_day, index_signal = 0, 0
        day = data_query.trade_days[no_day]
        if_stop_loss = False

        while no_day < len(data_query.trade_days):
            day = data_query.trade_days[no_day]

            if not if_stop_loss:
                open_price, high_price, low_price, close_price = (
                    data_query.open_price[no_day],
                    data_query.high_price[no_day],
                    data_query.low_price[no_day],
                    data_query.close_price[no_day],
                )

                if index_signal >= len(trade_order.time):
                    break
                else:
                    if_stop_loss, origin_dir = self.account.do_stop_loss(
                        trade_order.time[index_signal],
                        trade_order.code,
                        open_price,
                        high_price,
                        low_price,
                        close_price,
                    )

            cur_time, signal, price = (
                trade_order.time[index_signal],
                trade_order.signal[index_signal],
                trade_order.prices[index_signal],
            )
            while cur_time.date() <= day.date():
                if signal != signal:
                    index_signal += 1
                    if index_signal == len(trade_order.signal):
                        break
                    cur_time, signal, price = (
                        trade_order.time[index_signal],
                        trade_order.signal[index_signal],
                        trade_order.prices[index_signal],
                    )
                    continue
                n, direction = self.account.get_position_by_code(trade_order.code)
                if (
                    direction is None
                    and signal
                    and (not if_stop_loss or signal2dir(signal) != origin_dir)
                ):
                    for _ in range(trade_order.shares):
                        self.account.open_pos(
                            trade_order.code,
                            price,
                            signal2dir(signal),
                            trade_order.stop_loss,
                            cur_time,
                        )
                    if_stop_loss = False
                elif direction != signal2dir(signal):
                    close_dir = "long" if direction == "short" else "short"
                    for _ in range(n):
                        target_trade = self.account.get_target_close_trade(
                            trade_order.code, close_dir
                        )
                        self.account.close_pos(
                            trade_order.code, price, close_dir, target_trade, cur_time
                        )
                    if signal and (not if_stop_loss or signal2dir(signal) != origin_dir):
                        for _ in range(trade_order.shares):
                            res = self.account.open_pos(
                                trade_order.code, price, close_dir, trade_order.stop_loss, cur_time
                            )
                            if not res:
                                if_stop_loss = True
                                break
                        if_stop_loss = False
                index_signal += 1
                if index_signal == len(trade_order.signal):
                    break
                cur_time, signal, price = (
                    trade_order.time[index_signal],
                    trade_order.signal[index_signal],
                    trade_order.prices[index_signal],
                )

            self.account.MTM(margin_call, day)
            daily_balances[day] = {"balance": self.account.balance}
            no_day += 1

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
