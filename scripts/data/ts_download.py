from datetime import datetime
from functools import lru_cache

import pandas as pd
from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import HistoryRequest

from config.loader import DB_CONFIG as db_config
from get_data import freq_dict, normalize_exchange
from vnpy_adaptor import df2BarList, my_sql_database, ts_df


@lru_cache(maxsize=1)
def _get_db_query():
    return my_sql_database()


@lru_cache(maxsize=1)
def _get_ts_api():
    return ts_df(db_config.get("tushare_token", None))


# 通过csv读取数据并写入本地数据库
def save_csv_bar(
    csv_file, index_col, code, interval: str | Interval, exchange: Exchange | str | None = None
):
    """
    csv表头必须是open high low close
    index_col是时间戳的列名
    code是合约名，品种代码+YY年份+MM月份，注意没有交易所名
    exchange和interval分别是交易所和数据频率，注意是vnpy的相应数据格式
    """
    demo_data = pd.read_csv(csv_file)
    new_cols = {
        col: col + "_price"
        for col in demo_data.columns
        if col in ["open", "high", "low", "close", "settle"]
    }
    new_cols.update({index_col: "datetime"})

    exchange = normalize_exchange(code, exchange)
    if exchange is None:
        raise ValueError(
            "Unable to determine exchange. "
            "Please provide exchange explicitly or check EXCHANGE_MAP config."
        )
    if isinstance(interval, str):
        interval = freq_dict.get(interval, Interval.DAILY)

    demo_data["symbol"] = [code] * len(demo_data)
    demo_data["exchange"] = [exchange] * len(demo_data)
    demo_data["interval"] = [interval] * len(demo_data)

    list_bar = df2BarList(demo_data.rename(columns=new_cols))
    db_query = _get_db_query()
    db_query.save_bar_data(list_bar)
    return True


def save_ts_bar(code, exchange: Exchange, start: datetime, end: datetime, interval: Interval):
    ts_api = _get_ts_api()
    req = HistoryRequest(symbol=code, exchange=exchange, start=start, end=end, interval=interval)
    data = ts_api.query_bar_history(req)
    db_query = _get_db_query()
    db_query.save_bar_data(data)
    return True


def save_ts_contr(code, exchange: Exchange, start: datetime, end: datetime):
    ts_api = _get_ts_api()
    req = HistoryRequest(
        symbol=code, exchange=exchange, start=start, end=end, interval=Interval.DAILY
    )
    try:
        data = ts_api.query_contract_data(req)
    except ValueError as e:
        print(f"Error fetching contract data for {code}: {e}")
        return False
    db_query = _get_db_query()
    db_query.save_contr_info(data)
    return True
