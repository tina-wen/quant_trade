from datetime import datetime

from vnpy.trader.constant import Interval

from core.account_statistics import acc_stats
from core.simulation import TradeOrder, trade_simulation
from get_data import DataQuery
from scripts.get_args import get_args
from signals import get_signal


def run_backtest(data_query: DataQuery, args) -> trade_simulation:
    """Run the full backtest pipeline on a DataQuery and return the simulation result."""
    account = acc_stats(args.init_fund, args.shares, usr_name=args.usr_name, log_dir=args.log_dir)
    signal = get_signal(args.trade_strategy, args.config, data_query)
    trade_order = TradeOrder(
        signal, data_query.target_price, args.code, args.interval, args.stop_loss, args.shares
    )
    simu = trade_simulation(account)
    simu.calc_performances(trade_order, args.margin_call, data_query)
    return simu


if __name__ == "__main__":
    args = get_args()

    if args.sim:
        # Simulation mode: generate synthetic bars via fake_stream, bypass the database.
        import pandas as pd

        from get_data import fake_stream, freq_dict, normalize_exchange

        interval_enum = freq_dict.get(args.interval, Interval.DAILY)
        exchange_enum = normalize_exchange(args.code)

        bars = list(
            fake_stream(
                symbol=args.code,
                exchange=exchange_enum,
                interval=interval_enum,
                num_klines=args.sim_num_klines,
                volatility=args.sim_volatility,
            )
        )
        price_df = pd.DataFrame(
            [
                {
                    "datetime": b.datetime,
                    "open": b.open_price,
                    "high": b.high_price,
                    "low": b.low_price,
                    "close": b.close_price,
                    "settle": b.settle_price,
                }
                for b in bars
            ]
        ).set_index("datetime")
        data_query = DataQuery.from_price_df(
            price_df, args.code, exchange_enum, interval_enum, target=args.target
        )
        args.interval = interval_enum
        print(f"[sim] Generated {len(bars)} synthetic bars for {args.code}")
    else:
        # Normal mode: load historical data from the database.
        start_time = datetime.strptime(args.start_time, "%Y-%m-%d")
        end_time = datetime.strptime(args.end_time, "%Y-%m-%d")
        interval_enum = Interval.DAILY
        data_query = DataQuery(args.code, start_time, end_time, interval_enum, target=args.target)
        args.interval = interval_enum

    run_backtest(data_query, args)
