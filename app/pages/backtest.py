from datetime import datetime

import pandas as pd
import streamlit as st

from app.perf import init_page_profiler
from app.utils import get_available_contracts, get_available_times, get_strategy_names
from core.account_statistics import acc_stats
from core.simulation import TradeOrder, trade_simulation

profiler = init_page_profiler("backtest")

st.title("回测参数")
available_contracts = get_available_contracts()
profiler.mark("读取合约列表")
code = st.selectbox("选择合约代码", available_contracts)
trade_strategy = st.selectbox("选择交易策略", get_strategy_names())
profiler.mark("基础选择控件")


def get_st_configs() -> dict:
    # 根据策略名获取配置
    # 下拉列表选择trade_strategy
    # 对于ma策略，需要用户手动输入滞后期参数lag
    if trade_strategy == "ma":
        lag = st.number_input("滞后期", min_value=1, value=5)
    elif trade_strategy == "dma":
        short = st.number_input("短期均线周期", min_value=1, value=5)
        long = st.number_input("长期均线周期", min_value=short + 1, value=20)
    elif trade_strategy == "mr":
        lag = st.number_input("滞后期", min_value=1, value=5)
        threshold = st.number_input("阈值", min_value=0.0, value=1.0)
    elif trade_strategy == "qtl":
        ubr = st.number_input("上轨比例", min_value=0.0, max_value=1.0, value=0.75)
        lbr = st.number_input("下轨比例", min_value=0.0, max_value=1.0, value=0.25)
    elif trade_strategy == "abs":
        level = st.number_input(
            "水平线",
        )  # 没有手动输入的话，没有默认值
    elif trade_strategy == "mom":
        lag = st.number_input("滞后期", min_value=1, value=5)
    # 信号产生列名和交易价格列名
    source = st.selectbox("产生信号的变量名", ["open", "high", "low", "close", "settle"])
    # 根据上述变量名和值，生成一个字典
    config = {
        "source": source,
        "lag": lag if "lag" in locals() else None,
        "short": short if "short" in locals() else None,
        "long": long if "long" in locals() else None,
        "threshold": threshold if "threshold" in locals() else None,
        "ubr": ubr if "ubr" in locals() else None,
        "lbr": lbr if "lbr" in locals() else None,
        "level": level if "level" in locals() else None,
    }

    return config


init_fund = st.number_input("初始资金", value=100000.0)
margin_call = st.number_input("保证金追保线（默认为初始资金*0.1）", value=init_fund * 0.1)
# 交易手数
shares = st.number_input("交易手数", min_value=1, value=1)
# 止损设置
stop_loss = st.number_input("止损设置（例如：0.05 或 1000）", value=0.05)
# 滑点设置
slippage = st.number_input(
    "滑点百分比（买入加价/卖出减价，例如 0.001 表示 0.1%）", min_value=0.0, value=0.0, format="%f"
)
# 交易日志.log存放路径
log_dir = st.text_input("交易日志存放路径", value="./logs")

# 策略选择
target = st.selectbox("交易的价格", ["open", "high", "low", "close", "settle"])

# start_time不准超过early
early, late = get_available_times(code)
profiler.mark("读取可用时间区间")
if early is None or late is None:
    st.warning("该合约暂无可用时间区间，请先写入数据")
    st.stop()
# streamlit设置以日历的方式选择年月日和时分秒
start_date, start_time = (
    st.date_input("开始日期", value=pd.to_datetime(early)),
    st.time_input("开始时刻", value=datetime.strptime("00:00:00", "%H:%M:%S").time()),
)
end_date, end_time = (
    st.date_input("结束时间", value=pd.to_datetime(late)),
    st.time_input("结束时刻", value=datetime.strptime("23:59:59", "%H:%M:%S").time()),
)
start, end = datetime.combine(start_date, start_time), datetime.combine(end_date, end_time)

# 交易频率
interval = st.selectbox("交易频率", ["d", "w", "1m", "1h"])
profiler.mark("参数区渲染")

# 回测
### 根据收盘价生成的信号（当日3点后出），最早只能用开盘价交易
config = get_st_configs()

if st.button("开始回测"):
    profiler.mark("开始回测")
    from get_data import DataQuery
    from signals import get_signal

    test_account = acc_stats(init_fund, shares, usr_name="demo", log_dir=log_dir, slippage=slippage)
    data_query = DataQuery(code, start, end, interval, target=target)
    # todo: 未来需要支持.csv格式文件拖拽上传后处理成统一信号格式

    signal = get_signal(
        trade_strategy,
        config,
        data_query,
    )
    simu = trade_simulation(test_account)
    trade_order = TradeOrder(signal, data_query.target_price, code, interval, stop_loss, shares)
    simu.calc_performances(trade_order, margin_call, data_query)
    profiler.mark("回测计算完成")

    # 展示回测结果
    # 画一个折线图展示每日权益
    # 折线图起个名字
    st.subheader("每日权益")
    st.line_chart(simu.pnl["balance"], use_container_width=True)
    st.subheader("每日浮动盈亏")
    # 画一个柱状图显示每日盈亏，要显示图的名字
    st.bar_chart(simu.pnl["daily_profit"], use_container_width=True)
    # 画一个表格展示回测统计结果
    perf_df = pd.DataFrame.from_dict(simu.perf_dict, orient="index", columns=["值"])
    st.table(perf_df)

    st.success("回测完成")
    profiler.mark("结果渲染完成")

st.divider()
st.subheader("模拟实时回测")

sim_num_klines = st.number_input("模拟K线数量", min_value=10, value=200)
sim_volatility = st.slider("价格波动率", min_value=0.001, max_value=0.1, value=0.02, step=0.001)

if st.button("开始模拟"):
    from get_data import DataQuery as _DQ
    from get_data import fake_stream, normalize_exchange, normalize_interval
    from signals import get_signal as _get_signal

    interval_enum = normalize_interval(interval)
    exchange_enum = normalize_exchange(code)
    if exchange_enum is None:
        st.error(f"无法识别合约 {code} 对应的交易所，请检查合约代码后重试。")
        st.stop()

    try:
        bars = list(
            fake_stream(
                symbol=code,
                exchange=exchange_enum,
                interval=interval_enum,
                num_klines=int(sim_num_klines),
                volatility=sim_volatility,
            )
        )
    except ValueError as exc:
        st.error(f"模拟参数无效：{exc}")
        st.stop()
    except Exception as exc:
        st.error(f"模拟数据加载失败，请稍后重试：{exc}")
        st.stop()

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

    sim_data_query = _DQ.from_price_df(price_df, code, exchange_enum, interval_enum, target=target)

    sim_account = acc_stats(init_fund, shares, usr_name="sim", log_dir=log_dir, slippage=slippage)
    signal = _get_signal(trade_strategy, config, sim_data_query)
    sim_trade_order = TradeOrder(
        signal, sim_data_query.target_price, code, interval_enum, stop_loss, shares
    )
    sim_simu = trade_simulation(sim_account)
    sim_simu.calc_performances(sim_trade_order, margin_call, sim_data_query)

    st.subheader("模拟每日权益")
    st.line_chart(sim_simu.pnl["balance"], use_container_width=True)
    st.subheader("模拟每日浮动盈亏")
    st.bar_chart(sim_simu.pnl["daily_profit"], use_container_width=True)
    perf_df = pd.DataFrame.from_dict(sim_simu.perf_dict, orient="index", columns=["值"])
    st.table(perf_df)
    st.success(f"模拟完成，共处理 {len(bars)} 条K线")

profiler.render()
