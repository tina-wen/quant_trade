import random
from datetime import date, datetime, timedelta
from datetime import time as dt_time
from functools import lru_cache
from typing import Dict, Iterator, Optional

import holidays
import pandas as pd
from vnpy.trader.constant import Exchange, Interval

from vnpy_adaptor import BarDataV2, my_sql_database

price_cols = ["datetime", "open_price", "high_price", "close_price", "low_price", "settle_price"]

INTERVAL_ALIASES = {
    "m": Interval.MINUTE.value,
    "h": Interval.HOUR.value,
    "d": Interval.DAILY.value,
    "w": Interval.WEEKLY.value,
}
DEFAULT_SESSION_PROFILE = {
    "day_sessions": [["09:00", "10:15"], ["10:30", "11:30"], ["13:30", "15:00"]],
    "night_sessions": [],
    "auction": {"day": ["08:55", "09:00"]},
    "has_night": False,
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


def normalize_interval(interval: Interval | str) -> Interval:
    """Normalize user input into vn.py Interval values such as 1m, 1h, d, and w."""
    if isinstance(interval, Interval):
        return interval

    normalized_value = INTERVAL_ALIASES.get(interval.strip().lower(), interval.strip().lower())
    return Interval(normalized_value)


@lru_cache(maxsize=1)
def get_trading_session_config() -> dict:
    from config.loader import TRADING_SESSION_CONFIG

    return TRADING_SESSION_CONFIG


@lru_cache(maxsize=None)
def get_holiday_calendar(year: int):
    return holidays.China(years=[year])


def is_trading_day(day: date) -> bool:
    return day.weekday() < 5 and day not in get_holiday_calendar(day.year)


def next_trading_day(day: date) -> date:
    next_day = day + timedelta(days=1)
    while not is_trading_day(next_day):
        next_day += timedelta(days=1)
    return next_day


def _get_product_code(symbol: str) -> str:
    return "".join(ch for ch in symbol.split(".")[0] if ch.isalpha()).upper()


def _parse_session_time(value: str) -> dt_time:
    return datetime.strptime(value, "%H:%M").time()


def _to_local_naive_datetime(dt: datetime) -> datetime:
    """Normalize input datetimes for session comparisons.

    Trading session windows are built as naive local datetimes. Convert timezone-aware
    values to Asia/Shanghai first, then drop timezone info for safe comparisons.
    """
    ts = pd.Timestamp(dt)
    if ts.tzinfo is not None:
        ts = ts.tz_convert("Asia/Shanghai").tz_localize(None)
    return ts.to_pydatetime()


def get_session_profile(symbol: str, exchange: Exchange | None) -> dict:
    config = get_trading_session_config()
    profile: dict = dict(DEFAULT_SESSION_PROFILE)

    exchange_defaults = config.get("exchange_defaults", {})
    exchange_profile = exchange_defaults.get(exchange.value, {}) if exchange is not None else {}
    profile.update(exchange_profile)

    product_profile = config.get("product_overrides", {}).get(_get_product_code(symbol), {})
    profile.update(product_profile)

    merged_auction = dict(exchange_profile.get("auction", profile.get("auction", {})))
    merged_auction.update(product_profile.get("auction", {}))
    profile["auction"] = merged_auction
    profile["has_night"] = bool(profile.get("has_night") and profile.get("night_sessions"))
    return profile


def _get_session_windows_for_date(
    session_date: date, profile: dict
) -> list[tuple[datetime, datetime]]:
    if not is_trading_day(session_date):
        return []

    windows: list[tuple[datetime, datetime]] = []
    for start_str, end_str in profile.get("day_sessions", []):
        start_dt = datetime.combine(session_date, _parse_session_time(start_str))
        end_dt = datetime.combine(session_date, _parse_session_time(end_str))
        windows.append((start_dt, end_dt))

    if profile.get("has_night"):
        next_calendar_day = session_date + timedelta(days=1)
        if is_trading_day(next_calendar_day):
            for start_str, end_str in profile.get("night_sessions", []):
                start_dt = datetime.combine(session_date, _parse_session_time(start_str))
                end_dt = datetime.combine(session_date, _parse_session_time(end_str))
                if end_dt <= start_dt:
                    end_dt += timedelta(days=1)
                windows.append((start_dt, end_dt))

    return windows


def is_trading_time(
    dt: datetime,
    symbol: str,
    exchange: Exchange | str | None = None,
) -> bool:
    dt = _to_local_naive_datetime(dt)
    resolved_exchange = normalize_exchange(symbol, exchange)
    profile = get_session_profile(symbol, resolved_exchange)

    for session_date in (dt.date() - timedelta(days=1), dt.date()):
        for start_dt, end_dt in _get_session_windows_for_date(session_date, profile):
            if start_dt <= dt < end_dt:
                return True
    return False


def next_session_start(
    after_dt: datetime,
    symbol: str,
    exchange: Exchange | str | None = None,
) -> datetime:
    after_dt = _to_local_naive_datetime(after_dt)
    resolved_exchange = normalize_exchange(symbol, exchange)
    profile = get_session_profile(symbol, resolved_exchange)

    for offset in range(0, 14):
        session_date = after_dt.date() + timedelta(days=offset)
        for start_dt, _ in _get_session_windows_for_date(session_date, profile):
            if start_dt >= after_dt:
                return start_dt

    raise ValueError(f"No trading session found for {symbol} after {after_dt}")


def resolve_trade_date(
    dt: datetime,
    symbol: str,
    exchange: Exchange | str | None = None,
) -> date:
    dt = _to_local_naive_datetime(dt)
    resolved_exchange = normalize_exchange(symbol, exchange)
    profile = get_session_profile(symbol, resolved_exchange)

    for session_date in (dt.date() - timedelta(days=1), dt.date()):
        for start_dt, end_dt in _get_session_windows_for_date(session_date, profile):
            if start_dt <= dt < end_dt:
                if start_dt.time() >= dt_time(18, 0):
                    return next_trading_day(session_date)
                return session_date

    if is_trading_day(dt.date()):
        return dt.date()
    return next_trading_day(dt.date())


def _get_interval_step(interval: Interval, interval_minutes: int = 1) -> timedelta:
    if interval == Interval.DAILY:
        return timedelta(days=1)
    if interval == Interval.WEEKLY:
        return timedelta(weeks=1)
    if interval == Interval.HOUR:
        return timedelta(hours=1)
    return timedelta(minutes=max(interval_minutes, 1))


def _get_day_close_time(profile: dict) -> dt_time:
    end_times = [_parse_session_time(end_str) for _, end_str in profile.get("day_sessions", [])]
    return max(end_times) if end_times else dt_time(15, 0)


def next_trading_timestamp(
    current_time: datetime,
    interval: Interval | str,
    symbol: str,
    exchange: Exchange | str | None = None,
    interval_minutes: int = 1,
) -> datetime:
    current_time = _to_local_naive_datetime(current_time)
    interval = normalize_interval(interval)
    resolved_exchange = normalize_exchange(symbol, exchange)
    profile = get_session_profile(symbol, resolved_exchange)

    if interval in {Interval.DAILY, Interval.WEEKLY}:
        next_day = resolve_trade_date(current_time, symbol, resolved_exchange)
        steps = 1 if interval == Interval.DAILY else 5
        for _ in range(steps):
            next_day = next_trading_day(next_day)
        return datetime.combine(next_day, _get_day_close_time(profile))

    candidate = current_time + _get_interval_step(interval, interval_minutes)
    if is_trading_time(candidate, symbol, resolved_exchange):
        return candidate
    return next_session_start(candidate, symbol, resolved_exchange)


class Cache:
    _cache: Dict[str, any] = {}

    @classmethod
    def call(cls, func, code: str, trade_date: datetime, key: str = "times", **kwargs):
        trade_day = resolve_trade_date(trade_date, code)
        cache_key = f"{code}_{trade_day.isoformat()}_{key}"
        price = kwargs.get("price")
        if price is not None:
            cache_key = f"{cache_key}_{round(float(price), 6)}"

        if cache_key in cls._cache:
            return cls._cache[cache_key]
        # Execute and cache on first call.
        result = func(code, trade_date, key, **kwargs)
        cls._cache[cache_key] = result
        return result


def get_overview_df():
    return get_db_query().get_overview_df()


def get_contract_info(code: str, trade_date: datetime, key: str, price: float = None):
    code = code.split(".")[0]
    resolved_exchange = normalize_exchange(code)
    trading_day = resolve_trade_date(trade_date, code, resolved_exchange)
    trade_date = datetime.combine(trading_day, dt_time(0, 0))
    data_query = get_db_query()
    contr = data_query.load_contr_info(symbol=code, start=trade_date, end=trade_date)
    if len(contr) == 0:
        # Fallback to the latest available contract record up to trade_date.
        # Some datasets may miss a specific day's contract row while nearby days exist.
        lookback_start = trade_date - timedelta(days=31)
        fallback = data_query.load_contr_info(symbol=code, start=lookback_start, end=trade_date)
        if len(fallback) == 0:
            raise KeyError(
                "Contract "
                f"{code}: no contract info found on or before "
                f"{trade_date.strftime('%Y-%m-%d')} "
                "within the lookback window; data may be missing in database"
            )
        contr = [fallback[-1]]
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
    interval = normalize_interval(interval)
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
    price_df = data[price_cols].set_index("datetime").sort_index()
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
        self.interval = normalize_interval(interval)
        price_df = get_price_by_code(code, start_time, end_time, self.interval, self.exchange)
        price_df.columns = [x.replace("_price", "") for x in price_df.columns]
        self.price = price_df.sort_index()
        self.bar_times = self.price.index.tolist()
        self.trade_dates = [
            resolve_trade_date(dt, self.code, self.exchange) for dt in self.bar_times
        ]
        self.trade_days = [
            datetime.combine(trade_day, dt_time(0, 0))
            for trade_day in sorted(set(self.trade_dates))
        ]
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
        obj.interval = normalize_interval(interval)
        obj.price = price_df.sort_index()
        obj.bar_times = obj.price.index.tolist()
        obj.trade_dates = [resolve_trade_date(dt, code, exchange) for dt in obj.bar_times]
        obj.trade_days = [
            datetime.combine(trade_day, dt_time(0, 0)) for trade_day in sorted(set(obj.trade_dates))
        ]
        obj.settle_price = obj.price["settle"]
        obj.open_price = obj.price["open"].tolist()
        obj.high_price = obj.price["high"].tolist()
        obj.low_price = obj.price["low"].tolist()
        obj.target_price = obj.price[target] if target is not None else obj.price["close"]
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

    interval = normalize_interval(interval)

    if start_price is None:
        start_price = 100.0

    if num_klines <= 0:
        return

    query = db_query or get_db_query()
    current_price = float(start_price)
    step = _get_interval_step(interval, interval_minutes)
    current_time = start_time or (datetime.now() - step * num_klines)

    if interval in {Interval.DAILY, Interval.WEEKLY}:
        profile = get_session_profile(symbol, resolved_exchange)
        current_time = datetime.combine(
            resolve_trade_date(current_time, symbol, resolved_exchange),
            _get_day_close_time(profile),
        )
    elif not is_trading_time(current_time, symbol, resolved_exchange):
        current_time = next_session_start(current_time, symbol, resolved_exchange)

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
        current_time = next_trading_timestamp(
            current_time,
            interval,
            symbol,
            resolved_exchange,
            interval_minutes=interval_minutes,
        )
