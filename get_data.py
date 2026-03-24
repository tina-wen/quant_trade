from datetime import datetime
from functools import lru_cache
from typing import Dict

import pandas as pd
from vnpy.trader.constant import Exchange, Interval

from vnpy_adaptor import my_sql_database

price_cols = ["datetime", "open_price", "high_price", "close_price", "low_price", "settle_price"]

freq_dict = {
    "周": Interval.WEEKLY,
    "分钟": Interval.MINUTE,
    "日线": Interval.DAILY,
    "小时": Interval.HOUR,
}
Ex_dict = {"SHFE": Exchange.SHFE, "INE": Exchange.INE, "DCE": Exchange.DCE, "CZCE": Exchange.CZCE}
EXCHANGE_ALIAS_MAP = {
    "ZCE": "CZCE",
}


def _to_exchange(exchange_code: str) -> Exchange:
    normalized_code = EXCHANGE_ALIAS_MAP.get(exchange_code.upper(), exchange_code.upper())
    try:
        return Exchange(normalized_code)
    except ValueError:
        try:
            return Exchange[normalized_code]
        except KeyError as exc:
            raise ValueError(f"不支持的交易所: {exchange_code}") from exc


@lru_cache(maxsize=1)
def get_db_query():
    # Reuse a single database client in the process to avoid reconnect cost on each rerun.
    return my_sql_database()


def normalize_exchange(code: str, exchange: Exchange | str | None = None) -> Exchange | None:
    code = code.split(".")[0]

    if isinstance(exchange, Exchange):
        return exchange

    if isinstance(exchange, str):
        return _to_exchange(exchange)

    from config.loader import EXCHANGE_MAP

    inferred_exchange = EXCHANGE_MAP.get("".join(c for c in code if c.isalpha()).upper(), None)
    if isinstance(inferred_exchange, str):
        return _to_exchange(inferred_exchange)
    return inferred_exchange


class Cache:
    _cache: Dict[str, any] = {}

    @classmethod
    def call(cls, func, code: str, trade_date: datetime, key: str = "times", **kwargs):
        if code + "_" + key in cls._cache:
            return cls._cache[code + "_" + key]
        # 首次调用，执行 func 并缓存
        result = func(code, trade_date, key, **kwargs)
        cls._cache[code + "_" + key] = result
        return result


def get_overview_df():
    data_query = get_db_query()
    list_bar_overview = [x.__dict__["__data__"] for x in data_query.get_bar_overview()]
    overview_df = pd.DataFrame.from_records(list_bar_overview)
    return overview_df


# 获取合约结算信息
def get_contract_info(code: str, trade_date: datetime, key: str, price: float = None):
    code = code.split(".")[0]
    trade_date = trade_date.replace(hour=0, minute=0, second=0, microsecond=0)
    data_query = get_db_query()
    contr = data_query.load_contr_info(symbol=code, start=trade_date, end=trade_date)
    if len(contr) == 0:
        raise KeyError(
            f"合约{code}:{trade_date.strftime('%Y-%m-%d')}不是交易日或数据库中没有{trade_date.strftime('%Y-%m-%d')}的合约结算数据"
        )
    contr_dict = contr[0].__dict__

    ### 保证金和手续费的计算封装，不暴露原始数据
    # 计算保证金占用，入参key必含'margin'
    if "margin" in key:
        margin = contr_dict.get(key, None)
        if price and margin < 1:
            return margin * price
        return margin

    # 计算手续费，入参key必含'fee'
    if key == "today_offset_fee":
        return contr_dict.get(key, None)
    if key == "fee":
        fee, fee_rate = contr_dict["fee"], contr_dict["fee_rate"]
        return max(fee, price * fee_rate)

    return contr_dict[key]


# 基于合约代码，从数据库读取一段时期的K线价格，并以dataframe格式返回
def get_price_by_code(
    code: str,
    start_time: datetime,
    end_time: datetime,
    interval: str | Interval,
    exchange: Exchange | str | None = None,
):
    exchange = normalize_exchange(code, exchange)
    if isinstance(interval, str):
        interval = freq_dict.get(interval, Interval.DAILY)
    data_query = get_db_query()
    list_bar = data_query.load_bar_data(
        symbol=code, exchange=exchange, start=start_time, end=end_time, interval=interval
    )
    data = pd.DataFrame.from_records([x.__dict__ for x in list_bar])
    if len(data) == 0:
        start_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
        end_str = end_time.strftime("%Y-%m-%d %H:%M:%S")
        raise KeyError(
            f"本地数据库中没有{code}合约在{start_str}到{end_str}的数据，"
            "请核对时间范围或自行下载写入"
        )
    price_df = data[price_cols].set_index("datetime")
    return price_df


class DataQuery:
    def __init__(
        self,
        code: str,
        start_time: datetime,
        end_time: datetime,
        interval: Interval,
        target: str | None = None,
        exchange: Exchange | str | None = None,
    ):
        code = code.split(".")[0]
        self.code = code  # 合约代码
        self.exchange = normalize_exchange(code, exchange)
        price_df = get_price_by_code(
            code, start_time, end_time, interval, self.exchange
        )  # 完整的单合约的价格序列，符合一般量价数据格式，包括开收高低、结算价等
        self.trade_days = price_df.index.tolist()
        price_df.columns = [x.replace("_price", "") for x in price_df.columns]
        self.price = price_df
        self.settle_price = self.price["settle"]
        (
            self.open_price,
            self.high_price,
            self.low_price,
        ) = list(
            map(
                lambda key: self._get_price_by_key(key).tolist(),
                [
                    "open",
                    "high",
                    "low",
                ],
            )
        )
        if target is not None:
            self.target_price = self.price[target]
            self.close_price = self.target_price.tolist()

    def _get_price_by_key(self, key: str):
        return self.price[key]
