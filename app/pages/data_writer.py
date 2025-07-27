
# 怎么跨层级调用utils中导入的包
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils import st,get_available_contracts,get_exchange,freq_dict,Ex_dict,save_ts_contr,save_csv_bar,save_ts_bar


st.title("数据写入本地MySQL")

# st.header("数据下载至本地MySQL")

data_source = st.radio("数据源", [".csv", "Tushare"])

code = st.text_input("合约代码",) 

start_date = st.date_input("开始日期",)
end_date = st.date_input("结束日期",)

# 合约信息数据库里不存在该合约时，加载日度信息
if code not in get_available_contracts():
    exchange = Ex_dict[st.selectbox("选择交易所", ["SHFE", "DCE", "CZCE", "INE"])]
    if st.button("写入日度结算数据") and save_ts_contr(code, exchange, start_date, end_date):
        st.success("日度结算数据写入成功")
else:
    exchange = get_exchange(code)

interval = freq_dict[st.selectbox("数据频率", ["日线", "小时", "分钟", "周"])]

if data_source == ".csv":
    uploaded_file = st.file_uploader("上传.csv文件", type="csv")
    # st交互输入时间戳列的名字
    time_col = st.text_input("时间戳列名", value="Unnamed: 0")
    if uploaded_file:
        if st.button("写入K线数据") and save_csv_bar(uploaded_file, time_col, code, interval):
            st.success("K线数据写入成功")
elif data_source == "Tushare":
    if st.button("写入K线数据") and save_ts_bar(code,exchange,start_date,end_date,interval):
        st.success("K线数据写入成功")