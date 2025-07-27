# 不同类型数据与vnpy内置类BarData和TickData的转换
from vnpy_mysql.mysql_database import DbBarData,DbTickData,DbBarOverview,DbTickOverview,MysqlDatabase
from peewee import chunked,Model,CharField,DateTimeField,IntegerField,DoubleField,MySQLDatabase
from vnpy.trader.object import BarData,TickData,BaseData
from vnpy.trader.constant import Exchange,Interval
from datetime import datetime
from vnpy.trader.database import DB_TZ

from copy import deepcopy
import tushare as ts
from vnpy_tushare import Datafeed
from vnpy_tushare.tushare_datafeed import to_ts_symbol, INTERVAL_VT2TS, INTERVAL_ADJUSTMENT_MAP, CHINA_TZ
from vnpy.trader.utility import round_to

import json
from functools import partial

# 在BarData类添加settle_price字段
from dataclasses import dataclass
@dataclass
class BarDataV2(BarData):
    settle_price: float = 0.0

BarData = BarDataV2

# 定义新的数据类，合约的相关信息
@dataclass
class ContractData(BaseData):
    symbol: str 
    exchange: Exchange
    date: datetime

    # 报价倍数
    times: float = 0.0

    ### 以下可能随时间变化
    # 交易手续费（率）
    fee: float = 0.0
    fee_rate: float = 0.0
    today_offset_fee: float = 0.0
    # 保证金（率）
    long_margin: float = 0.0  # 多头保证金率
    short_margin: float = 0.0  # 空头保证金率


def df2BarList(df_input):
    # 取得BarData的字段
    fields = BarDataV2.__dataclass_fields__
    # req_cols = list(fields.keys())
    req_cols = [x for x in fields.keys() if x in df_input.columns]
    # 转为numpy_ndarray读取效率高于遍历DataFrame?
    np_data = df_input[req_cols].to_numpy()
    # 预分配List<BarData>内存
    result = [None]*len(df_input)
    for i in range(len(df_input)):
        args = {col:np_data[i,j] for j,col in enumerate(req_cols)}
        if 'gateway_name' not in args:
            args['gateway_name'] = 'wtf'
        if isinstance(args['datetime'],str):
            from dateutil import parser
            args['datetime'] = parser.parse(args['datetime'])
        # 通过dataclass装饰的纯数据类，直接以字典形式实例化
        result[i] = BarDataV2(**args)
    return result



# 补丁：动态传入mysql连接参数
def patched_db_models(models: list[Model], db: MySQLDatabase):
    for model in models:
        if hasattr(model,'_meta'):
            model._meta.database = db
         


def get_db_config(json_path:str = "database_config.json"):
    with open(json_path,"r") as f:
        configs = json.load(f)
    db = MySQLDatabase(
            configs.get("db_name",""),
            user=configs.get("db_user",""),
            password=configs.get("db_pwd",""),
            host=configs.get("db_host","")
            )
    return db

patched_db_models([DbBarData,DbTickData,DbBarOverview,DbTickOverview],get_db_config())

# 新增数据库model，用于读写contract相关数据


class DbContractData(Model):
    # 合约代码、交易所、时间戳
    symbol: CharField = CharField()
    exchange: CharField = CharField()
    date: DateTimeField = DateTimeField()

    times: IntegerField = IntegerField()
    fee: DoubleField = DoubleField()
    fee_rate: DoubleField = DoubleField()
    today_offset_fee: DoubleField = DoubleField()

    long_margin: DoubleField = DoubleField()
    short_margin: DoubleField = DoubleField()

    class Meta:
        database = get_db_config()
        indexes: tuple = ((("symbol", "date"), True),)

DbBarData._meta.add_field('settle_price', DoubleField())

class my_sql_database(MysqlDatabase):
    def __init__(self,):
        self.db = get_db_config()
        self.db.connect()
        tables = [DbBarData, DbTickData, DbContractData, DbBarOverview, DbTickOverview]
        new_tables = [x for x in tables if not x.table_exists()]
        self.db.create_tables(new_tables)

    def load_bar_data(
        self,
        symbol: str,
        exchange: Exchange,
        interval: Interval,
        start: datetime,
        end: datetime
    ) -> list[BarDataV2]:
        """"""
        s: ModelSelect = (
            DbBarData.select().where(
                (DbBarData.symbol == symbol)
                & (DbBarData.exchange == exchange.value)
                & (DbBarData.interval == interval.value)
                & (DbBarData.datetime >= start)
                & (DbBarData.datetime <= end)
            ).order_by(DbBarData.datetime)
        )

        bars: list[BarData] = []
        for db_bar in s:
            bar: BarDataV2 = BarDataV2(
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
                gateway_name="DB"
            )
            bars.append(bar)

        return bars

    def save_contr_info(self,contr_data: list[ContractData]):
        contr_info: ContractData = contr_data[0]
        symbol: str = contr_info.symbol
        exchange: Exchange = contr_info.exchange
        data: list = []

        for contr in contr_data:
            d: dict = contr.__dict__
            d["exchange"] = d["exchange"].value
            d.pop("gateway_name")
            data.append(d)

        with self.db.atomic():
            for c in chunked(data,50):
                DbContractData.insert_many(c).on_conflict_replace().execute()

    def load_contr_info(self, symbol: str, start, end):
        s: ModelSelect = (
                DbContractData.select().where(
                    (DbContractData.symbol == symbol)
                    & (DbContractData.date >= start)
                    & (DbContractData.date <= end)
                    ).order_by(DbContractData.date)
                )

        contracts: list[ContractData] = []
        for contract in s:
            contr: ContractData = ContractData(
                    symbol = contract.symbol,
                    exchange = Exchange(contract.exchange),
                    date = datetime.fromtimestamp(contract.date.timestamp(),DB_TZ),
                    times = contract.times,
                    fee = contract.fee,
                    fee_rate = contract.fee_rate,
                    today_offset_fee = contract.today_offset_fee,
                    long_margin = contract.long_margin,
                    short_margin = contract.short_margin,
                    gateway_name = "DB"
                    )
            contracts.append(contr)
        return contracts

    
# tushare_datafeed的api适配


class ts_df(Datafeed):
    def __init__(self,ts_pwd,ts_usr='token'):
        super().__init__()
        self.username = ts_usr
        self.password = ts_pwd

    def init(self, output=print):
        super().init(output)
        # Interval不支持Monthly
        self.apis = dict(zip([Interval.WEEKLY, Interval.DAILY, Interval.HOUR, Interval.MINUTE], 
                             [
                                partial(self.pro.fut_weekly_monthly,freq='week'), 
                                self.pro.fut_daily,
                                partial(self.pro.ft_mins, freq = '60min'),
                                partial(self.pro.ft_mins, freq = '1min')
                            ]))

    # query_bar_data加一个字段settle_price
    def query_bar_history(self, req, output = print) -> list[BarDataV2]:
        """查询k线数据"""
        if not self.inited:
            self.init(output)

        start: datetime = req.start.strftime("%Y-%m-%d %H:%M:%S")
        end: datetime = req.end.strftime("%Y-%m-%d %H:%M:%S")

        ts_symbol: str  = to_ts_symbol(req.symbol, req.exchange)
        if not ts_symbol:
            return None

        adjustment: timedelta = INTERVAL_ADJUSTMENT_MAP.get(req.interval, 0)
        api_inputs = {'ts_code': ts_symbol, 'start_date': start, 'end_date': end, }
        if req.interval.value == 'd' or req.interval.value == 'w':
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
            tmp_end: str = d1["trade_time"].values[-1]

            d1 = self.apis[req.interval](**api_inputs)
            df = pd.concat([df[:-1], d1])

        bar_keys: list[datetime] = []
        bar_dict: dict[datetime, BarDataV2] = {}
        data: list[BarDataV2] = []

        # 处理原始数据中的NaN值
        df.fillna(0, inplace=True)

        if df is not None:
            for _ix, row in df.iterrows():
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
                settle_price = row.get("settle",0) # 日内没有结算价数据

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
                    gateway_name="TS"
                )

                bar_dict[dt] = bar
        bar_keys = sorted(bar_dict.keys(), reverse=False)
        for i in bar_keys:
            data.append(bar_dict[i])

        return data
    
    def query_contract_data(self, req, output = print) -> list[ContractData] :
        """查每日结算数据"""
        if not self.inited:
            self.init(output)

        symbol: str = req.symbol
        exchange: Exchange = req.exchange
        start: str = req.start.strftime("%Y%m%d")
        end: str = req.end.strftime("%Y%m%d")

        ts_symbol: str  = to_ts_symbol(symbol, exchange)
        if not ts_symbol:
            return None

        try:
            df: DataFrame = self.pro.fut_settle(
                ts_code=ts_symbol,
                start_date=start,
                end_date=end,
                fields = 'trade_date,trading_fee,trading_fee_rate,long_margin_rate,short_margin_rate,offset_today_fee'
            )
            if len(df) == 0:
                raise ValueError(f"未成功从tushare数据库中取得{ts_symbol}在{start}~{end}时期的合约数据，数据条数为0")
            # 取出某个交易所（某个品种）所有合约的报价倍数
            trade_code = ts_symbol.split('.')[0]
            fut_code = "".join([x for x in trade_code if x.isalpha()])
            times_df = self.pro.fut_basic(exchange=exchange.value, fut_code=fut_code, fields='ts_code,per_unit').set_index('ts_code')
            times = times_df['per_unit'].loc[ts_symbol].item()
        except OSError as ex:
            output(f"发生输入/输出错误：{ex.strerror}")
            return []

        contr_keys: list[datetime] = []
        contr_dict: dict[datetime, ContractData] = {}
        data: list[ContractData] = []

        # 处理原始数据中的NaN值
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
                    gateway_name="TS"
                )

                contr_dict[dt] = contr_info

        contr_keys = sorted(contr_dict.keys(), reverse=False)
        for i in contr_keys:
            data.append(contr_dict[i])

        return data


