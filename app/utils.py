# 调用上级目录get_data模块中的函数
# 如果用相对导入（如 from ..get_data import ...），上级目录必须是包（有 __init__.py）
# 如果不想新建 __init__.py，可以用绝对路径或动态修改 sys.path：
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# 然后用绝对导入

from get_data import overview_df,get_exchange,freq_dict,Ex_dict,DataQuery,data_query
from signals import get_signal
from core.simulation import trade_simulation, TradeOrder, acc_stats
from ts_download import save_csv_bar, save_ts_bar, save_ts_contr
import streamlit as st


def get_available_contracts() -> list:
    # 这里可以从数据库或其他数据源获取合约列表
    return overview_df['symbol'].unique().tolist()

def get_contract_info(code: str,) -> dict:
    # 从overview_df中获取合约信息
    if code in overview_df['symbol'].values:
        return overview_df[overview_df['symbol'] == code].iloc[0].to_dict()
    else:
        st.error(f"合约 {code} 不存在")
        return {}
    
def get_available_times(code) -> list:
        # 这里可以从数据源获取可用日期列表
        info_dict = get_contract_info(code, )
        start = info_dict.get('start', )
        end = info_dict.get('end',)
        return start, end

def get_strategy_names() -> list:
    # 返回注册策略名列表
    return ["ma", "dma", "mr","qtl","abs","mom"]