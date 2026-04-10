from datetime import datetime

import pandas as pd
import streamlit as st

from app.utils import get_available_contracts
from core.simulation import TradeOrder, acc_stats, trade_simulation
from get_data import DataQuery, Ex_dict, get_overview_df, normalize_interval
from scripts.data.ts_download import save_csv_bar, save_ts_bar, save_ts_contr
from signals import get_signal


def get_strategy_names() -> list:
    # 返回注册策略名列表
    return ["ma", "dma", "mr", "qtl", "abs", "mom"]


def get_contract_info(
    code: str,
) -> dict:
    # 从overview_df中获取合约信息
    overview_df = get_overview_df()
    if code in overview_df["symbol"].values:
        return overview_df[overview_df["symbol"] == code].iloc[0].to_dict()
    else:
        st.error(f"合约 {code} 不存在")
        return {}


def get_available_times(code) -> list:
    # 这里可以从数据源获取可用日期列表
    info_dict = get_contract_info(
        code,
    )
    start = info_dict.get(
        "start",
    )
    end = info_dict.get(
        "end",
    )
    return start, end


st.set_page_config(page_title="量化回测平台", layout="wide")
st.title("📈 量化策略回测平台")


# streamlit有几个可切换的页面
def download_data_from_tushare():
    st.header("数据下载至本地MySQL")

    data_source = st.radio("数据源", [".csv", "Tushare"])

    code = st.text_input(
        "合约代码",
    )

    start_date = st.date_input(
        "开始日期",
    )
    end_date = st.date_input(
        "结束日期",
    )

    # 合约信息数据库里不存在该合约时，加载日度信息
    if code not in get_available_contracts():
        exchange = Ex_dict[st.selectbox("选择交易所", ["SHFE", "DCE", "CZCE", "INE"])]
        if st.button("写入日度结算数据") and save_ts_contr(code, exchange, start_date, end_date):
            st.success("日度结算数据写入成功")
    else:
        from config.loader import EXCHANGE_MAP

        exchange = EXCHANGE_MAP.get("".join(c for c in code if c.isalpha()), None)

    interval = normalize_interval(st.selectbox("数据频率", ["d", "1m", "1h", "w"]))

    if data_source == ".csv":
        uploaded_file = st.file_uploader("上传.csv文件", type="csv")
        # st交互输入时间戳列的名字
        time_col = st.text_input("时间戳列名", value="Unnamed: 0")
        if uploaded_file:
            if st.button("写入K线数据") and save_csv_bar(uploaded_file, time_col, code, interval):
                st.success("K线数据写入成功")
    elif data_source == "Tushare":
        if st.button("写入K线数据") and save_ts_bar(code, exchange, start_date, end_date, interval):
            st.success("K线数据写入成功")


def backtest_vis():
    # 在streamlit新开一个页面，名为策略配置
    st.header("策略配置")
    trade_strategy = st.selectbox("选择交易策略", get_strategy_names())

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
            level = st.number_input("水平线", min_value=0.0, value=4500.00)
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

    code = st.selectbox("选择合约代码", get_available_contracts())
    init_fund = st.number_input("初始资金", value=100000.0)
    margin_call = st.number_input("保证金追保线（默认为初始资金*0.1）", value=init_fund * 0.1)
    # 交易手数
    shares = st.number_input("交易手数", min_value=1, value=1)
    # 止损设置
    stop_loss = st.number_input("止损设置（例如：0.05 或 1000）", value=0.05)
    # 交易日志.log存放路径
    log_dir = st.text_input("交易日志存放路径", value="./logs")

    # 策略选择
    target = st.selectbox("交易的价格", ["open", "high", "low", "close", "settle"])

    # start_time不准超过early
    early, late = get_available_times(code)
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
    interval = st.selectbox(
        "交易频率",
        [
            "d",
            "1m",
            "1h",
            "w",
        ],
    )

    # 回测
    ### 根据收盘价生成的信号（当日3点后出），最早只能用开盘价交易
    config = get_st_configs()

    if st.button("开始回测"):
        test_account = acc_stats("demo", init_fund, log_dir, shares)
        data_query = DataQuery(code, start, end, interval, target=target)
        # todo: 未来需要支持.csv格式文件拖拽上传后处理成统一信号格式

        signal = get_signal(
            trade_strategy,
            config,
            data_query,
        )
        simu = trade_simulation(test_account)
        trade_order = TradeOrder(signal, data_query.target_price, code, interval, stop_loss, shares)
        simu.calc_performances(start, end, trade_order, margin_call, data_query)

        # 展示回测结果
        st.subheader("回测结果")
        # 画一个折线图展示每日权益
        st.line_chart(simu.pnl["balance"], use_container_width=True)
        # 画一个柱状图显示每日盈亏，要显示图的名字
        st.bar_chart(simu.pnl["daily_profit"], use_container_width=True)
        # 画一个表格展示回测统计结果
        perf_df = pd.DataFrame.from_dict(simu.perf_dict, orient="index", columns=["值"])
        st.table(perf_df)

        st.success("回测完成")


if __name__ == "__main__":
    download_data_from_tushare()
    backtest_vis()
