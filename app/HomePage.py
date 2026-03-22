import streamlit as st

from app.perf import init_page_profiler

profiler = init_page_profiler("HomePage")

st.title("期货量化回测平台")
profiler.mark("标题渲染")
# 页面导航
st.sidebar.title("导航")
st.sidebar.markdown("""
- [数据写入](./data_writer)
- [策略回测](./backtest)
""")
profiler.mark("侧边栏渲染")
# 页面内容：分点列举目前支持功能
st.write("目前支持功能：")
st.markdown("""
- 从tushare下载K线和日度结算数据到本地MySQL
- 从本地.csv文件写入K线数据到MySQL
- 策略回测：单双均线、动量策略、均值回归等
- 回测结果可视化：盈亏曲线、持仓曲线、交易日志等
- 回测结果统计：年化收益率、最大回撤、夏普比率
- 支持多种交易频率：日线、分钟、周等
""")
profiler.mark("当前功能区块")

st.write("计划支持功能：")
st.markdown("""
- 策略优化：参数优化、组合优化等
- 策略组合：多策略组合回测
- 新策略封装：ideas from 研报或论文
""")
profiler.mark("计划功能区块")

st.write("局限:")
st.markdown("""
- Tushare不支持上期所SHFE和能源所INE以外的合约结算数据
- 分钟/小时(60m)数据，非氪金账号不能取，实测10000积分不能用
""")
profiler.mark("局限区块")

st.write(
    "需求和建议请在开源项目[GitHub](https://github.com/tina-wen/quant_trade/tree/master#)上提issue，欢迎star和fork！"
)
profiler.mark("页面收尾")
profiler.render()
