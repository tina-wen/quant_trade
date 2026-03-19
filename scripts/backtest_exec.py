from datetime import datetime

from vnpy.trader.constant import Interval

from core.account_statistics import acc_stats
from core.simulation import TradeOrder, trade_simulation
from get_data import DataQuery
from scripts.get_args import get_args
from signals import get_signal

if __name__ == "__main__":
    args = get_args()

    ### 测试账户创建 ###
    test_account = acc_stats(
        args.init_fund, args.shares, usr_name=args.usr_name, log_dir=args.log_dir
    )

    ### 根据收盘价生成的信号（当日3点后出），最早只能用开盘价交易
    start_time, end_time = (
        datetime.strptime(args.start_time, "%Y-%m-%d"),
        datetime.strptime(args.end_time, "%Y-%m-%d"),
    )
    data_query = DataQuery(args.code, start_time, end_time, Interval.DAILY, target=args.target)
    signal = get_signal(
        args.trade_strategy,
        args.config,
        data_query,
    )

    simu = trade_simulation(test_account)
    trade_order = TradeOrder(
        signal, data_query.target_price, args.code, Interval.DAILY, args.stop_loss, args.shares
    )
    simu.calc_performances(trade_order, args.margin_call, data_query)
