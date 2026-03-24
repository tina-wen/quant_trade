import streamlit as st

from app.perf import init_page_profiler
from config.loader import EXCHANGE_MAP
from get_data import freq_dict, get_db_query, get_overview_df, normalize_exchange

profiler = init_page_profiler("data_writer")


def _extract_variety(code: str) -> str:
    code = (code or "").split(".")[0]
    return "".join(ch for ch in code if ch.isalpha()).upper()


def _normalize_exchange_code(exchange_code: str | None) -> str | None:
    if exchange_code is None:
        return None
    exchange_code = exchange_code.upper()
    if exchange_code == "ZCE":
        return "CZCE"
    return exchange_code


st.title("数据写入本地MySQL")

# st.header("数据下载至本地MySQL")

data_source = st.radio(
    "数据源",
    [
        "Tushare",
        ".csv",
    ],
)

code = st.text_input(
    "合约代码",
)
profiler.mark("基础输入控件")

has_code = bool(code.strip())
variety = _extract_variety(code) if has_code else ""
inferred_exchange_code = _normalize_exchange_code(EXCHANGE_MAP.get(variety)) if has_code else None

start_date = st.date_input(
    "开始日期",
)
end_date = st.date_input(
    "结束日期",
)
profiler.mark("日期控件")

if has_code and inferred_exchange_code:
    st.info(f"根据合约代码识别到品种 {variety}，交易所：{inferred_exchange_code}")
    exchange = normalize_exchange(code, inferred_exchange_code)
else:
    if has_code:
        st.warning("未在 exchange_map.json 中匹配到该品种，请手动选择交易所")
    manual_exchange_options = ["SHFE", "DCE", "CZCE", "INE", "CFFEX", "GFEX"]
    mapped_exchange_options = [
        _normalize_exchange_code(x) for x in EXCHANGE_MAP.values() if _normalize_exchange_code(x)
    ]
    for exchange_code in mapped_exchange_options:
        if exchange_code not in manual_exchange_options:
            manual_exchange_options.append(exchange_code)
    selected_exchange = st.selectbox("选择交易所", manual_exchange_options)
    exchange = normalize_exchange(code, selected_exchange)
profiler.mark("交易所识别")

# 合约信息数据库里不存在该合约时，加载日度信息
if st.button("检查合约结算信息"):
    profiler.mark("开始检查结算信息")
    from scripts.data.ts_download import save_ts_contr

    data_query = get_db_query()
    dq_res = data_query.load_contr_info(symbol=code, start=start_date, end=end_date)
    if len(dq_res) == 0:
        # if st.button("写入合约结算信息"):
        if save_ts_contr(code, exchange, start_date, end_date):
            st.success("合约结算信息写入成功")
    else:
        st.success(f"合约结算信息已存在，交易所为{exchange}")
    profiler.mark("完成检查结算信息")

raw_interval = st.selectbox("数据频率", ["日线", "小时", "分钟", "周"])
interval = freq_dict[raw_interval]
profiler.mark("频率选择")

if data_source == ".csv":
    uploaded_file = st.file_uploader("上传.csv文件", type="csv")
    # st交互输入时间戳列的名字
    time_col = st.text_input("时间戳列名", value="Unnamed: 0")
    if uploaded_file:
        from scripts.data.ts_download import save_csv_bar

        if st.button("写入K线数据") and save_csv_bar(
            uploaded_file, time_col, code, interval, exchange
        ):
            st.success("K线数据写入成功")
            profiler.mark("CSV写入完成")
elif data_source == "Tushare":
    if st.button("写入K线数据"):
        profiler.mark("开始Tushare写入")
        from scripts.data.ts_download import save_ts_bar

        overview_df = get_overview_df()
        interval_value = interval.value if hasattr(interval, "value") else interval
        bar_req_res = overview_df[
            (overview_df["symbol"] == code) & (overview_df["interval"] == interval)
        ]
        if "interval" in overview_df.columns:
            bar_req_res = overview_df[
                (overview_df["symbol"] == code) & (overview_df["interval"] == interval_value)
            ]
        if len(bar_req_res) == 1:
            st.success(
                f"{code}的{raw_interval}K线数据已存在，区间从{bar_req_res['start'].values[0]}到{bar_req_res['end'].values[0]}"
            )
        elif len(bar_req_res) == 0:
            if save_ts_bar(code, exchange, start_date, end_date, interval):
                st.success("K线数据写入成功")
                profiler.mark("Tushare写入完成")

profiler.render()
