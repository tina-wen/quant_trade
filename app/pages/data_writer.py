import streamlit as st

from get_data import Ex_dict, freq_dict, get_overview_df
from scripts.data.ts_download import save_csv_bar, save_ts_bar, save_ts_contr
from vnpy_adaptor import my_sql_database

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

start_date = st.date_input(
    "开始日期",
)
end_date = st.date_input(
    "结束日期",
)

exchange = st.selectbox("选择交易所", ["SHFE", "DCE", "CZCE", "INE"])
exchange = Ex_dict[exchange]

data_query = my_sql_database()

# 合约信息数据库里不存在该合约时，加载日度信息
if st.button("检查合约结算信息"):
    dq_res = data_query.load_contr_info(symbol=code, start=start_date, end=end_date)
    if len(dq_res) == 0:
        # if st.button("写入合约结算信息"):
        if save_ts_contr(code, exchange, start_date, end_date):
            st.success("合约结算信息写入成功")
    else:
        st.success(f"合约结算信息已存在，交易所为{exchange}")

raw_interval = st.selectbox("数据频率", ["日线", "小时", "分钟", "周"])
interval = freq_dict[raw_interval]

if data_source == ".csv":
    uploaded_file = st.file_uploader("上传.csv文件", type="csv")
    # st交互输入时间戳列的名字
    time_col = st.text_input("时间戳列名", value="Unnamed: 0")
    if uploaded_file:
        if st.button("写入K线数据") and save_csv_bar(
            uploaded_file, time_col, code, interval, exchange
        ):
            st.success("K线数据写入成功")
elif data_source == "Tushare":
    if st.button("写入K线数据"):
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
