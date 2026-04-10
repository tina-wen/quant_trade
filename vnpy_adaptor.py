# Adapters between project data and vn.py BarData/TickData models.
import logging
from collections import deque
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import partial

import pandas as pd
from pandas import DataFrame
from peewee import (
    CharField,
    DateTimeField,
    DoubleField,
    IntegerField,
    Model,
    ModelSelect,
    MySQLDatabase,
    chunked,
)
from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.database import DB_TZ
from vnpy.trader.object import BarData, BaseData
from vnpy.trader.utility import round_to
from vnpy_mysql.mysql_database import (
    DbBarData,
    DbBarOverview,
    DbTickData,
    DbTickOverview,
    MysqlDatabase,
)
from vnpy_tushare import Datafeed
from vnpy_tushare.tushare_datafeed import (
    CHINA_TZ,
    INTERVAL_ADJUSTMENT_MAP,
    to_ts_symbol,
)


@dataclass
class BarDataV2(BarData):
    settle_price: float = 0.0


BarData = BarDataV2


@dataclass
class ContractData(BaseData):
    symbol: str
    exchange: Exchange
    date: datetime

    # Contract multiplier.
    times: float = 0.0

    # Fee fields, can vary over time.
    fee: float = 0.0
    fee_rate: float = 0.0
    today_offset_fee: float = 0.0
    long_margin: float = 0.0
    short_margin: float = 0.0
    settle: float = 0.0


def df2BarList(df_input):
    fields = BarDataV2.__dataclass_fields__
    req_cols = [x for x in fields.keys() if x in df_input.columns]
    np_data = df_input[req_cols].to_numpy()
    result = [None] * len(df_input)
    for i in range(len(df_input)):
        args = {col: np_data[i, j] for j, col in enumerate(req_cols)}
        if "gateway_name" not in args:
            args["gateway_name"] = "wtf"
        if isinstance(args["datetime"], str):
            from dateutil import parser

            args["datetime"] = parser.parse(args["datetime"])
        result[i] = BarDataV2(**args)
    return result


def patched_db_models(models: list[Model], db: MySQLDatabase):
    for model in models:
        if hasattr(model, "_meta"):
            model._meta.database = db


def get_db_config():
    from config.loader import DB_CONFIG as configs

    db = MySQLDatabase(
        configs.get("db_name", ""),
        user=configs.get("db_user", ""),
        password=configs.get("db_pwd", ""),
        host=configs.get("db_host", ""),
    )
    return db


patched_db_models([DbBarData, DbTickData, DbBarOverview, DbTickOverview], get_db_config())


class DbContractData(Model):
    symbol: CharField = CharField()
    exchange: CharField = CharField()
    date: DateTimeField = DateTimeField()

    times: IntegerField = IntegerField()
    fee: DoubleField = DoubleField()
    fee_rate: DoubleField = DoubleField()
    today_offset_fee: DoubleField = DoubleField()

    long_margin: DoubleField = DoubleField()
    short_margin: DoubleField = DoubleField()
    settle: DoubleField = DoubleField()

    class Meta:
        database = get_db_config()
        indexes: tuple = ((("symbol", "date"), True),)


DbBarData._meta.add_field("settle_price", DoubleField())


class my_sql_database(MysqlDatabase):
    def __init__(
        self,
        batch_size: int = 10000,
        buffer_size: int = 500,
    ):
        """Initialize database client with isolated history/realtime buffer sizes.

        batch_size controls history loading chunk size and _history_buffer max length.
        buffer_size controls realtime context size and _realtime_buffer max length.
        """
        self.db = get_db_config()
        self.db.connect()
        self.batch_size = max(batch_size, 1)
        self.buffer_size = max(buffer_size, 1)
        # Realtime path: keep only the latest N bars per symbol.
        self._realtime_buffer: dict[tuple, deque[BarDataV2]] = {}
        # History path: isolated buffer for chunked historical loading.
        self._history_buffer: dict[str, deque[BarDataV2]] = {}
        tables = [DbBarData, DbTickData, DbContractData, DbBarOverview, DbTickOverview]
        new_tables = [x for x in tables if not x.table_exists()]
        self.db.create_tables(new_tables)

    def _build_bar_query(
        self,
        symbol: str,
        exchange: Exchange,
        interval: Interval,
        start: datetime,
        end: datetime,
    ) -> ModelSelect:
        conditions = (
            (DbBarData.symbol == symbol)
            & (DbBarData.interval == interval.value)
            & (DbBarData.datetime >= start)
            & (DbBarData.datetime <= end)
        )
        if exchange is not None:
            conditions = conditions & (DbBarData.exchange == exchange.value)

        return DbBarData.select().where(conditions)

    @staticmethod
    def _to_bar_data(db_bar: DbBarData) -> BarDataV2:
        return BarDataV2(
            symbol=db_bar.symbol,
            exchange=Exchange(db_bar.exchange),
            datetime=datetime.fromtimestamp(db_bar.datetime.timestamp(), DB_TZ),
            interval=Interval(db_bar.interval),
            volume=db_bar.volume,
            turnover=db_bar.turnover,
            open_interest=db_bar.open_interest,
            open_price=db_bar.open_price,
            high_price=db_bar.high_price,
            low_price=db_bar.low_price,
            close_price=db_bar.close_price,
            settle_price=db_bar.settle_price,
            gateway_name="DB",
        )

    def _iter_bar_data(
        self, symbol: str, exchange: Exchange, interval: Interval, start: datetime, end: datetime
    ):
        s: ModelSelect = self._build_bar_query(symbol, exchange, interval, start, end).order_by(
            DbBarData.datetime
        )

        found = False
        for db_bar in s.iterator():
            found = True
            yield self._to_bar_data(db_bar)

        if not found:
            logging.warning("no data found for %s between %s and %s", symbol, start, end)

    def init_realtime_buffer(
        self,
        symbol: str,
        exchange: Exchange,
        interval: Interval,
        lookback_days: int = 30,
        end: datetime | None = None,
    ) -> deque[BarDataV2]:
        end_dt = end or datetime.now(DB_TZ)
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=DB_TZ)
        start_dt = end_dt - timedelta(days=lookback_days)

        s: ModelSelect = (
            self._build_bar_query(symbol, exchange, interval, start_dt, end_dt)
            .order_by(DbBarData.datetime.desc())
            .limit(self.buffer_size)
        )

        recent_bars = [self._to_bar_data(db_bar) for db_bar in s.iterator()]
        recent_bars.reverse()
        if not recent_bars:
            logging.warning("no data found for %s between %s and %s", symbol, start_dt, end_dt)

        buffer: deque[BarDataV2] = deque(recent_bars, maxlen=self.buffer_size)
        buf_key = (symbol, exchange.value, interval.value)
        self._realtime_buffer[buf_key] = buffer
        return buffer

    def append_kline(
        self, symbol: str, kline: BarDataV2, lookback_days: int = 30
    ) -> deque[BarDataV2]:
        if symbol != kline.symbol:
            raise ValueError(f"symbol={symbol} does not match kline.symbol={kline.symbol}")

        buf_key = (symbol, kline.exchange.value, kline.interval.value)
        if buf_key not in self._realtime_buffer:
            self.init_realtime_buffer(
                symbol=symbol,
                exchange=kline.exchange,
                interval=kline.interval,
                lookback_days=lookback_days,
                end=kline.datetime,
            )

        self._realtime_buffer[buf_key].append(kline)
        return self._realtime_buffer[buf_key]

    def load_bar_data(
        self, symbol: str, exchange: Exchange, interval: Interval, start: datetime, end: datetime
    ):
        if symbol not in self._history_buffer:
            self._history_buffer[symbol] = deque(maxlen=self.batch_size)

        chunk: list[BarDataV2] = []
        for bar in self._iter_bar_data(symbol, exchange, interval, start, end):
            self._history_buffer[symbol].append(bar)
            chunk.append(bar)
            if len(chunk) >= self.batch_size:
                yield chunk
                chunk = []

        if chunk:
            yield chunk

    def get_overview_df(self) -> DataFrame:
        overview_rows = [
            {field_name: getattr(item, field_name) for field_name in item._meta.sorted_field_names}
            for item in self.get_bar_overview()
        ]
        return pd.DataFrame.from_records(overview_rows)

    def save_contr_info(self, contr_data: list[ContractData]):
        data: list = []

        for contr in contr_data:
            d: dict = contr.__dict__
            d["exchange"] = d["exchange"].value
            d.pop("gateway_name")
            data.append(d)

        with self.db.atomic():
            for c in chunked(data, 50):
                DbContractData.insert_many(c).on_conflict_replace().execute()

    def load_contr_info(self, symbol: str, start, end):
        s: ModelSelect = (
            DbContractData.select()
            .where(
                (DbContractData.symbol == symbol)
                & (DbContractData.date >= start)
                & (DbContractData.date <= end)
            )
            .order_by(DbContractData.date)
        )

        contracts: list[ContractData] = []
        for contract in s:
            contr: ContractData = ContractData(
                symbol=contract.symbol,
                exchange=Exchange(contract.exchange),
                date=datetime.fromtimestamp(contract.date.timestamp(), DB_TZ),
                times=contract.times,
                fee=contract.fee,
                fee_rate=contract.fee_rate,
                today_offset_fee=contract.today_offset_fee,
                long_margin=contract.long_margin,
                short_margin=contract.short_margin,
                settle=contract.settle,
                gateway_name="DB",
            )
            contracts.append(contr)
        return contracts


class ts_df(Datafeed):
    def __init__(self, ts_pwd, ts_usr="token"):
        super().__init__()
        self.username = ts_usr
        self.password = ts_pwd

    def init(self, output=print):
        super().init(output)
        # Monthly is not supported by Interval.
        self.apis = dict(
            zip(
                [Interval.WEEKLY, Interval.DAILY, Interval.HOUR, Interval.MINUTE],
                [
                    partial(self.pro.fut_weekly_monthly, freq="week"),
                    self.pro.fut_daily,
                    partial(self.pro.ft_mins, freq="60min"),
                    partial(self.pro.ft_mins, freq="1min"),
                ],
            )
        )

    def query_bar_history(self, req, output=print) -> list[BarDataV2]:
        """Query bar history and map to BarDataV2."""
        if not self.inited:
            self.init(output)

        start: datetime = req.start.strftime("%Y-%m-%d %H:%M:%S")
        end: datetime = req.end.strftime("%Y-%m-%d %H:%M:%S")

        ts_symbol: str = to_ts_symbol(req.symbol, req.exchange)
        if not ts_symbol:
            return None

        adjustment: timedelta = INTERVAL_ADJUSTMENT_MAP.get(req.interval, 0)
        api_inputs = {
            "ts_code": ts_symbol,
            "start_date": start,
            "end_date": end,
        }
        if req.interval.value == "d" or req.interval.value == "w":
            api_inputs.update(exchange=req.exchange.value)

        try:
            d1: DataFrame = self.apis[req.interval](**api_inputs)
        except OSError as ex:
            output(f"发生输入/输出错误：{ex.strerror}")
            return []
        df: DataFrame = deepcopy(d1)

        while True:
            if len(d1) != 8000:
                break

            d1 = self.apis[req.interval](**api_inputs)
            df = pd.concat([df[:-1], d1])

        bar_keys: list[datetime] = []
        bar_dict: dict[datetime, BarDataV2] = {}
        data: list[BarDataV2] = []

        df.fillna(0, inplace=True)

        if df is not None:
            for _, row in df.iterrows():
                if row["open"] is None:
                    continue

                if req.interval.value == "d" or req.interval.value == "w":
                    dt_str: str = row["trade_date"]
                    dt: datetime = datetime.strptime(dt_str, "%Y%m%d")
                else:
                    dt_str = row["trade_time"]
                    dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S") - adjustment

                dt = dt.replace(tzinfo=CHINA_TZ)

                turnover = row.get("amount", 0)
                open_interest = row.get("oi", 0)
                settle_price = row.get("settle", 0)

                bar: BarDataV2 = BarDataV2(
                    symbol=req.symbol,
                    exchange=req.exchange,
                    interval=req.interval,
                    datetime=dt,
                    open_price=round_to(row["open"], 0.000001),
                    high_price=round_to(row["high"], 0.000001),
                    low_price=round_to(row["low"], 0.000001),
                    close_price=round_to(row["close"], 0.000001),
                    settle_price=settle_price,
                    volume=row["vol"],
                    turnover=turnover,
                    open_interest=open_interest,
                    gateway_name="TS",
                )

                bar_dict[dt] = bar
        bar_keys = sorted(bar_dict.keys(), reverse=False)
        for i in bar_keys:
            data.append(bar_dict[i])

        return data

    def query_contract_data(self, req, output=print) -> list[ContractData]:
        """Query daily contract settlement data."""
        if not self.inited:
            self.init(output)

        symbol: str = req.symbol
        exchange: Exchange = req.exchange
        start: str = req.start.strftime("%Y%m%d")
        end: str = req.end.strftime("%Y%m%d")

        ts_symbol: str = to_ts_symbol(symbol, exchange)
        if not ts_symbol:
            return None

        try:
            df: DataFrame = self.pro.fut_settle(
                ts_code=ts_symbol,
                start_date=start,
                end_date=end,
                fields="trade_date,trading_fee,trading_fee_rate,long_margin_rate,short_margin_rate,offset_today_fee,settle",
            )
            if len(df) == 0:
                raise ValueError(
                    f"Failed to fetch contract data for {ts_symbol} between {start} and {end}: "
                    "received 0 rows"
                )
            # Load contract multiplier for this futures symbol.
            trade_code = ts_symbol.split(".")[0]
            fut_code = "".join([x for x in trade_code if x.isalpha()])
            times_df = self.pro.fut_basic(
                exchange=exchange.value, fut_code=fut_code, fields="ts_code,per_unit"
            ).set_index("ts_code")
            times = times_df["per_unit"].loc[ts_symbol].item()
        except OSError as ex:
            output(f"发生输入/输出错误：{ex.strerror}")
            return []

        contr_keys: list[datetime] = []
        contr_dict: dict[datetime, ContractData] = {}
        data: list[ContractData] = []

        df.fillna(0, inplace=True)

        if df is not None:
            for _ix, row in df.iterrows():
                dt_str: str = row["trade_date"]
                dt: datetime = datetime.strptime(dt_str, "%Y%m%d")

                dt = dt.replace(tzinfo=CHINA_TZ)

                contr_info: ContractData = ContractData(
                    symbol=symbol,
                    exchange=exchange,
                    date=dt,
                    times=times,
                    fee=row["trading_fee"],
                    fee_rate=row["trading_fee_rate"],
                    today_offset_fee=row["offset_today_fee"],
                    long_margin=row["long_margin_rate"],
                    short_margin=row["short_margin_rate"],
                    settle=row["settle"],
                    gateway_name="TS",
                )

                contr_dict[dt] = contr_info

        contr_keys = sorted(contr_dict.keys(), reverse=False)
        for i in contr_keys:
            data.append(contr_dict[i])

        return data
