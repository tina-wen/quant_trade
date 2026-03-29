import random
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Dict, Iterator, Optional

import pandas as pd
from vnpy.trader.constant import Exchange, Interval

from vnpy_adaptor import BarDataV2, my_sql_database

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
            raise ValueError(f"Unsupported exchange: {exchange_code}") from exc


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
        # Execute and cache on first call.
        result = func(code, trade_date, key, **kwargs)
        cls._cache[code + "_" + key] = result
        return result


def get_overview_df():
    return get_db_query().get_overview_df()


def get_contract_info(code: str, trade_date: datetime, key: str, price: float = None):
    code = code.split(".")[0]
    trade_date = trade_date.replace(hour=0, minute=0, second=0, microsecond=0)
    data_query = get_db_query()
    contr = data_query.load_contr_info(symbol=code, start=trade_date, end=trade_date)
    if len(contr) == 0:
        raise KeyError(
            f"Contract {code}: no settlement data found for {trade_date.strftime('%Y-%m-%d')} "
            "(non-trading day or missing in database)"
        )
    contr_dict = contr[0].__dict__

    # Expose derived margin/fee values instead of raw fields.
    if "margin" in key:
        margin = contr_dict.get(key, None)
        if price and margin < 1:
            return margin * price
        return margin

    if key == "today_offset_fee":
        return contr_dict.get(key, None)
    if key == "fee":
        fee, fee_rate = contr_dict["fee"], contr_dict["fee_rate"]
        return max(fee, price * fee_rate)

    return contr_dict[key]


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
    bar_batches = data_query.load_bar_data(
        symbol=code, exchange=exchange, start=start_time, end=end_time, interval=interval
    )

    rows = []
    for chunk in bar_batches:
        rows.extend(x.__dict__ for x in chunk)

    data = pd.DataFrame.from_records(rows)
    if len(data) == 0:
        start_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
        end_str = end_time.strftime("%Y-%m-%d %H:%M:%S")
        raise KeyError(
            f"No local database data for contract {code} between {start_str} and {end_str}. "
            "Please verify the time range or download and store the data first."
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
        self.code = code
        self.exchange = normalize_exchange(code, exchange)
        price_df = get_price_by_code(code, start_time, end_time, interval, self.exchange)
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
        self.target_price = self.price[target] if target is not None else self.price["close"]
        self.close_price = self.target_price.tolist()

    def _get_price_by_key(self, key: str):
        return self.price[key]

    @classmethod
    def from_price_df(
        cls,
        price_df: pd.DataFrame,
        code: str,
        exchange: Exchange,
        interval: Interval,
        target: str | None = None,
    ) -> "DataQuery":
        """Build a DataQuery from a prebuilt price DataFrame, bypassing the database.

        price_df must be indexed by datetime with columns: open, high, low, close, settle.
        """
        obj = cls.__new__(cls)
        obj.code = code
        obj.exchange = exchange
        obj.trade_days = price_df.index.tolist()
        obj.price = price_df
        obj.settle_price = price_df["settle"]
        obj.open_price = price_df["open"].tolist()
        obj.high_price = price_df["high"].tolist()
        obj.low_price = price_df["low"].tolist()
        obj.target_price = price_df[target] if target is not None else price_df["close"]
        obj.close_price = obj.target_price.tolist()
        return obj


def generate_fake_kline(
    symbol: str,
    exchange: Exchange,
    interval: Interval,
    base_price: float = 100.0,
    volatility: float = 0.02,
    current_time: Optional[datetime] = None,
) -> BarDataV2:
    """Generate one synthetic BarDataV2 for realtime simulation."""
    dt = current_time or datetime.now()
    change_pct = random.uniform(-volatility, volatility)
    close_price = base_price * (1 + change_pct)
    high_price = max(base_price, close_price) * (1 + random.uniform(0, volatility * 0.5))
    low_price = min(base_price, close_price) * (1 - random.uniform(0, volatility * 0.5))
    open_price = base_price
    volume = float(random.randint(100_000, 10_000_000))

    return BarDataV2(
        symbol=symbol,
        exchange=exchange,
        interval=interval,
        datetime=dt,
        open_price=round(open_price, 6),
        high_price=round(high_price, 6),
        low_price=round(low_price, 6),
        close_price=round(close_price, 6),
        settle_price=round(close_price, 6),
        volume=volume,
        turnover=round(close_price * volume, 6),
        open_interest=0.0,
        gateway_name="FAKE",
    )


def fake_stream(
    data_query: DataQuery | None = None,
    symbol: str | None = None,
    exchange: Exchange | str | None = None,
    interval: str | Interval = Interval.MINUTE,
    start_price: float | None = None,
    num_klines: int = 100,
    interval_minutes: int = 1,
    volatility: float = 0.02,
    start_time: datetime | None = None,
    db_query: my_sql_database | None = None,
) -> Iterator[BarDataV2]:
    """Yield synthetic bars and append each one via append_kline for simulation."""
    if data_query is not None:
        symbol = symbol or data_query.code
        exchange = exchange or data_query.exchange
        if start_price is None:
            start_price = float(data_query.close_price[-1])

    if not symbol:
        raise ValueError("symbol is required (provide symbol or data_query)")

    resolved_exchange = normalize_exchange(symbol, exchange)
    if resolved_exchange is None:
        raise ValueError("exchange is required (provide exchange or inferable symbol)")

    if isinstance(interval, str):
        interval = freq_dict.get(interval, Interval.MINUTE)

    if start_price is None:
        start_price = 100.0

    if num_klines <= 0:
        return

    query = db_query or get_db_query()
    current_price = float(start_price)
    step = timedelta(minutes=interval_minutes)
    current_time = start_time or (datetime.now() - step * num_klines)

    for _ in range(num_klines):
        kline = generate_fake_kline(
            symbol=symbol,
            exchange=resolved_exchange,
            interval=interval,
            base_price=current_price,
            volatility=volatility,
            current_time=current_time,
        )
        query.append_kline(symbol, kline)
        yield kline

        current_price = kline.close_price
        current_time = current_time + step
