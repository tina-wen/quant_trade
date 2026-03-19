import streamlit as st

from get_data import get_overview_df


@st.cache_data(ttl=300)
def _load_overview_df():
    return get_overview_df()


def get_available_contracts() -> list:
    overview_df = _load_overview_df()
    if overview_df.empty:
        return []
    return overview_df["symbol"].unique().tolist()


def get_contract_info(
    code: str,
) -> dict:
    overview_df = _load_overview_df()
    if code in overview_df["symbol"].values:
        return overview_df[overview_df["symbol"] == code].iloc[0].to_dict()
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


def get_strategy_names() -> list:
    # 返回注册策略名列表
    return ["ma", "dma", "mr", "qtl", "abs", "mom"]
