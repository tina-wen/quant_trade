import pandas as pd
from datetime import datetime
from vnpy_adaptor import my_sql_database
from vnpy.trader.constant import Exchange,Interval
from typing import Dict

price_cols = ['datetime','open_price','high_price','close_price','low_price','settle_price']

data_query = my_sql_database()
list_bar_overview = [x.__dict__['__data__'] for x in data_query.get_bar_overview()]
overview_df = pd.DataFrame.from_records(list_bar_overview)

freq_dict = {'周': Interval.WEEKLY, '分钟': Interval.MINUTE, '日线': Interval.DAILY}
Ex_dict = {"SHFE": Exchange.SHFE, "INE": Exchange.INE, "DCE": Exchange.DCE, "CZCE": Exchange.CZCE}

class TimesCache:
    _cache: Dict[str,datetime] = {}
    @classmethod
    def call(cls, func, code: str, trade_date: datetime, key: str = 'times'):
        if key == 'times':
            if code in cls._cache:
                return cls._cache[code]
            # 首次调用，执行 func 并缓存
            result = func(code, trade_date, key)
            cls._cache[code] = result
            return result
        return func(code, trade_date, key)  # 不缓存

# 基于合约代码获取交易所
def get_exchange(code:str):
    return overview_df.set_index('symbol')['exchange'].loc[code.split('.')[0]]
    
# 获取合约结算信息
def get_contract_info(code:str,trade_date:datetime,key:str,price:float = None):
    code = code.split('.')[0]

    contr = data_query.load_contr_info(symbol=code,start=trade_date,end=trade_date)
    if len(contr) == 0:
        raise KeyError(f'合约{code}:{trade_date.strftime("%Y-%m-%d")}不是交易日或数据库中没有{trade_date.strftime("%Y-%m-%d")}的合约结算数据')
    contr_dict = contr[0].__dict__

    ### 保证金和手续费的计算封装，不暴露原始数据
    # 计算保证金占用，入参key必含'margin'
    if 'margin' in key:
        margin = contr_dict.get(key,None)
        if price and margin < 1:
            return margin * price
        return margin

    # 计算手续费，入参key必含'fee'
    if key == 'today_offset_fee':
        return contr_dict.get(key,None)
    if key == 'fee':
        fee,fee_rate = contr_dict['fee'], contr_dict['fee_rate']
        return max(fee, price*fee_rate)

    return contr_dict[key]



# 基于合约代码，从数据库读取一段时期的K线价格，并以dataframe格式返回
def get_price_by_code(code: str, start_time: datetime, end_time: datetime, interval: str):
    exchange = get_exchange(code)
    interval = freq_dict.get(interval, Interval.DAILY)
    list_bar = data_query.load_bar_data(symbol=code,exchange=exchange,start=start_time,end=end_time,interval=interval)
    data = pd.DataFrame.from_records([x.__dict__ for x in list_bar])
    if len(data) == 0:
        raise KeyError(f"本地数据库中没有{code}合约在{start_time.strftime('%Y-%m-%d %H:%M:%S')}到{end_time.strftime('%Y-%m-%d %H:%M:%S')}的数据，请核对时间范围或自行下载写入")
    price_df = data[price_cols].set_index('datetime')
    return price_df


class DataQuery:
    def __init__(self, code: str, start_time: datetime, end_time: datetime, interval: Interval, target: str):
        code = code.split('.')[0]
        self.code = code  # 合约代码
        price_df = get_price_by_code(code, start_time, end_time, interval) # 完整的单合约的价格序列，符合一般量价数据格式，包括开收高低、结算价等
        self.trade_days = price_df.index.tolist()
        price_df.columns = [x.replace("_price","") for x in price_df.columns]
        self.price = price_df
        self.target_price, self.settle_price = self.price[target], self.price['settle']
        self.open_price, self.high_price, self.low_price, = list(map(lambda key: self._get_price_by_key(key).tolist(),["open","high","low",])) 
        self.close_price = self.target_price.tolist()

    def _get_price_by_key(self,key: str):
        return self.price[key]


