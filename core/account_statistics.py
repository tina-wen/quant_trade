import logging
import os
from collections import deque
from datetime import datetime

from get_data import Cache, get_contract_info, resolve_trade_date

from .utils import get_log_name


class trade_items:
    """
    TODO：应该是单例？？
    """

    def __init__(self, code: str, open_price: float, direction: str, stop_loss: float, open_time):
        # 生成一笔交易单号：用交易所或者自己生成
        # 记录开仓时间
        self.open_time = open_time
        # 开仓时新建一笔交易单实例
        self.code = code
        self.open_price = open_price
        self.prev_set_price = open_price
        self.direction = direction
        # 保证金占用
        # 对open_time做强制修改，日期不变，时间强制修改为00:00:00
        # 等价于 get_contract_info(..., direction+'_margin', price=open_price)
        self.margin = Cache.call(
            get_contract_info, code, open_time, direction + "_margin", price=open_price
        )
        # 开仓手续费
        self.commission = Cache.call(get_contract_info, code, open_time, "fee", price=open_price)
        # 交易盈利
        self.profit = 0
        # 该笔交易止损点
        if stop_loss > 1.0:
            self.stop_loss_point = stop_loss
        else:
            if self.direction == "short":
                self.stop_loss_point = open_price * (1 + stop_loss)
            elif self.direction == "long":
                self.stop_loss_point = open_price * (1 - stop_loss)

    def get_trade_commission(self, price: float, time):
        return Cache.call(get_contract_info, self.code, time, "fee", price=price)

    def get_profits(self):
        return self.profit

    def close_trade(self, close_price, direction, date):
        if direction == self.direction:
            raise ValueError(
                f"Invalid close direction: contract {self.code} position is {self.direction}, "
                f"close direction {direction} is not allowed"
            )
        times = Cache.call(get_contract_info, self.code, date, "times")
        if self.direction == "short":
            self.profit += (self.open_price - close_price) * times
        elif self.direction == "long":
            self.profit += (close_price - self.open_price) * times
        # 账户中平仓动作清零保证金必须在此之前
        self.margin = 0
        self.commission += self.get_trade_commission(close_price, date)


class acc_stats:
    def __init__(
        self,
        init_funds: float,
        shares: int,
        usr_name: str | None = None,
        log_dir: str | None = None,
    ):
        # 流动资金和权益，权益和现金的不同发生在逐日盯市和交易结算时
        self.init_bal = init_funds
        self.balance = init_funds
        self.funds = init_funds
        ###创建账户之后每笔交易单，字典key为合约名，value为该合约下的未平仓交易###
        self.open_trade_items = {}
        ###已平仓交易单
        self.close_trade_items = {}
        self.usr = usr_name if usr_name is not None else "default_user"
        # 记录日志
        if log_dir is not None:
            if not os.path.exists(log_dir):
                os.makedirs(log_dir)
            logging.basicConfig(
                filename=os.path.join(log_dir, get_log_name(shares)), level=logging.INFO
            )
            logging.info(f"User {self.usr} registered with initial funds {init_funds}")

    def get_total_margin(self):
        """
        账户总保证金占用
        """
        total_margin = 0
        for _, trades in self.open_trade_items.items():
            for trade in trades:
                total_margin += trade.margin
        return total_margin

    def get_position_by_code(self, code):
        """
        获取当前账户某个合约的持仓状况
        账户中不允许对同一个标的合约，同时具有多头和空头持仓
        """
        if code not in self.open_trade_items:
            return 0, None
        n = len(self.open_trade_items[code])
        if n == 0:
            direction = None
        else:
            direction = self.open_trade_items[code][0].direction
        return n, direction

    def open_pos(self, code: str, price: float, direction: str, stop_loss: tuple, time):
        # 判断能否开仓
        trade_item = trade_items(code, price, direction, stop_loss, time)
        margin, commission_fee = trade_item.margin, trade_item.get_trade_commission(price, time)
        if self.funds < margin + commission_fee:
            logging.error(f"{time}流动资金{self.funds}不足以开仓！")
            err_msg = f"{time}流动资金{self.funds}不足以开仓！"
            return err_msg
        self.funds -= margin + commission_fee
        self.balance -= commission_fee
        if code in self.open_trade_items:
            self.open_trade_items[code].append(trade_item)
        else:
            self.open_trade_items[code] = deque([trade_item])
        ###TODO:记录日志###
        logging.info(
            f"Trade day {time.strftime('%Y%m%d')}: opened 1 lot of {code}, direction={direction}, "
            f"open_price={price}, commission={commission_fee}, margin={margin}"
        )
        logging.info(f"Account equity={self.balance}, available funds={self.funds}")

    def get_target_close_trade(self, code, direction):
        """
        依据信号平仓（非止损平仓）
        找平仓单的时候，顺便就把self.open_trade_items修改了
        """
        ### 首先找出要平仓的交易单
        if len(self.open_trade_items[code]) == 0:
            logging.error(f"当前没有合约{code}的持仓！")
            raise KeyError(f"No open position found for contract {code}.")
        tmp_open_trade = self.open_trade_items[code].popleft()
        return tmp_open_trade

    # 平仓
    def close_pos(self, code, price, direction, target_trade, time):
        """
        对指定的某笔交易target_trade平仓
        """
        margin, commission_fee = target_trade.margin, target_trade.get_trade_commission(price, time)
        self.funds += margin - commission_fee
        target_trade.close_trade(price, direction, time)
        profit = target_trade.get_profits()
        self.funds += profit

        times = Cache.call(get_contract_info, code, time, "times")

        if direction == "long":
            self.balance += (target_trade.prev_set_price - price) * times
        elif direction == "short":
            self.balance += (price - target_trade.prev_set_price) * times

        self.balance -= commission_fee
        if code in self.close_trade_items:
            self.close_trade_items[code].append(target_trade)
        else:
            self.close_trade_items[code] = deque([target_trade])

        #### 记录交易日志
        logging.info(
            f"Trade day {time.strftime('%Y%m%d')}: closed 1 lot of {code}, direction={direction}, "
            f"close_price={price}, trade_profit={profit}, commission={commission_fee}"
        )
        logging.info(f"Current account equity={self.balance}, available funds={self.funds}")

    # 逐日盯市函数
    def MTM(self, limit, cur_trade_day: datetime):
        for contract, trades in self.open_trade_items.items():
            settle_price = Cache.call(get_contract_info, contract, cur_trade_day, "settle")

            times = Cache.call(get_contract_info, contract, cur_trade_day, "times")

            for trade in trades:
                if trade.direction == "long":
                    self.balance += (settle_price - trade.prev_set_price) * times
                    trade.prev_set_price = settle_price
                elif trade.direction == "short":
                    self.balance += (trade.prev_set_price - settle_price) * times
                    trade.prev_set_price = settle_price
        ###日志记录逐日盯市后结算的账户权益
        logging.info(
            f"Trade day {cur_trade_day.strftime('%Y%m%d')}: equity={self.balance}, "
            f"available_funds={self.funds}, total_margin={self.get_total_margin()}"
        )
        if self.balance < limit:
            logging.warning(f"账户权益为{self.balance}，已低于最低要求{limit}，请追加保证金！")

    # 止损函数
    def do_stop_loss(self, time, contract, *ohlc):
        """
        默认按照开盘价开仓，判断止损标准分别依据非当天的开盘价、高/低价和收盘价是否触及止损点
        """
        open_price, high_price, low_price, close_price = ohlc

        # 之前还没信号的时候，直接跳过，不必止损
        if contract not in self.open_trade_items:
            return False, None
        # 找到当前需要止损的第一单
        (tmp_trade_list,) = ([],)
        flag, direction = False, None
        while len(self.open_trade_items[contract]):
            trade = self.open_trade_items[contract].popleft()

            # 检查触发多头止损
            long_stop_loss = trade.direction == "long" and (
                (
                    resolve_trade_date(trade.open_time, contract)
                    < resolve_trade_date(time, contract)
                    and open_price <= trade.stop_loss_point
                )
                or min(close_price, low_price) <= trade.stop_loss_point
            )

            # 检查触发空头止损
            short_stop_loss = trade.direction == "short" and (
                (
                    resolve_trade_date(trade.open_time, contract)
                    < resolve_trade_date(time, contract)
                    and open_price >= trade.stop_loss_point
                )
                or max(close_price, high_price) >= trade.stop_loss_point
            )

            if long_stop_loss:
                self.close_pos(contract, trade.stop_loss_point, "short", trade, time)
                while len(tmp_trade_list):
                    self.open_trade_items[contract].appendleft(tmp_trade_list.pop())
                flag, direction = True, "long"
            elif short_stop_loss:
                self.close_pos(contract, trade.stop_loss_point, "long", trade, time)
                while len(tmp_trade_list):
                    self.open_trade_items[contract].appendleft(tmp_trade_list.pop())
                flag, direction = True, "short"
            # 本单未触发止损
            else:
                tmp_trade_list.append(trade)

        while len(tmp_trade_list):
            self.open_trade_items[contract].appendleft(tmp_trade_list.pop())

        return flag, direction  # 当日标的合约是否发生了止损，什么信号时发生的止损
