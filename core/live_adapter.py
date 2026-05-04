import logging
import queue
import signal as _signal
import threading
import time as _time
from collections import deque
from datetime import datetime
from typing import Callable

import pandas as pd
from vnpy.event import EventEngine
from vnpy.trader.constant import Direction, Exchange, Offset, OrderType
from vnpy.trader.engine import MainEngine
from vnpy.trader.object import CancelRequest, OrderRequest, SubscribeRequest
from vnpy.trader.utility import BarGenerator

from get_data import normalize_exchange

from .account_statistics import acc_stats

logger = logging.getLogger(__name__)

# 方向/开平 映射
_DIR_MAP = {
    "long": Direction.LONG,
    "short": Direction.SHORT,
}
_OFFSET_OPEN = Offset.OPEN
_OFFSET_CLOSE = Offset.CLOSE  # 平今/平昨由 vn.py 内部处理


class LiveAdapter:
    """
    实盘/模拟盘适配器，接口与 acc_stats 兼容。

    Parameters
    ----------
    gateway_name : str
        vn.py 网关名称，如 "CTP"、"XTP"。
    settings : dict
        网关连接参数字典（参考各网关文档）。
    init_funds : float
        初始资金（用于本地镜像账户统计）。
    shares : int
        默认每次开仓手数。
    slippage : float
        滑点百分比（与 acc_stats 一致）。
    log_dir : str | None
        日志目录。
    """

    def __init__(
        self,
        gateway_name: str,
        settings: dict,
        init_funds: float,
        shares: int = 1,
        slippage: float = 0.0,
        log_dir: str | None = None,
    ):
        self.gateway_name = gateway_name
        self.settings = settings
        self.shares = shares

        # 本地镜像账户：由 on_trade 回报驱动更新，用于绩效统计
        self._mirror = acc_stats(
            init_funds, shares, usr_name=f"live_{gateway_name}", log_dir=log_dir, slippage=slippage
        )

        # vn.py 引擎
        self._event_engine = EventEngine()
        self._main_engine = MainEngine(self._event_engine)

        # 等待回报的队列（send_order 可选同步等待）
        self._trade_queue: queue.Queue = queue.Queue()
        self._order_callbacks: list[Callable] = []
        self._trade_callbacks: list[Callable] = []

        # 已发出委托：{vt_orderid: (code, direction, offset, price)}
        self._pending_orders: dict[str, tuple] = {}
        self._lock = threading.Lock()

        self._connected = False

    # ──────────────────────────────────────────
    # 连接管理
    # ──────────────────────────────────────────

    def connect(self, timeout: float = 30.0):
        """连接网关，阻塞等待交易服务器登录结果。

        Parameters
        ----------
        timeout : float
            等待登录确认的最长秒数，默认 30s。超时或登录失败均抛出 RuntimeError。
        """
        try:
            gateway_cls = self._load_gateway(self.gateway_name)
        except ImportError as e:
            raise RuntimeError(
                f"无法加载网关 {self.gateway_name}，请确认已安装对应 vnpy 扩展包。\n{e}"
            )

        self._main_engine.add_gateway(gateway_cls)

        # ── 先启动事件引擎，再连接，确保日志事件能被消费 ──
        from vnpy.event import EVENT_LOG, EVENT_ORDER, EVENT_TRADE

        self._event_engine.register(EVENT_ORDER, self._on_order)
        self._event_engine.register(EVENT_TRADE, self._on_trade)
        self._event_engine.start()

        # 用临时 handler 监听交易服务器登录结果
        _login_done = threading.Event()
        _login_errors: list[str] = []
        _SUCCESS_KEYWORD = "交易服务器登录成功"
        _FAILURE_KEYWORDS = ("登录失败", "连接断开", "授权失败", "密码错误")

        def _on_login_log(event):
            msg: str = getattr(event.data, "msg", str(event.data))
            if _SUCCESS_KEYWORD in msg:
                _login_done.set()
            elif any(kw in msg for kw in _FAILURE_KEYWORDS):
                _login_errors.append(msg)
                _login_done.set()

        self._event_engine.register(EVENT_LOG, _on_login_log)
        self._main_engine.connect(self.settings, self.gateway_name)

        if not _login_done.wait(timeout=timeout):
            self._main_engine.close()
            self._event_engine.stop()
            raise RuntimeError(
                f"连接网关 {self.gateway_name} 超时（{timeout}s），请检查网络和前置地址是否正确。"
            )

        self._event_engine.unregister(EVENT_LOG, _on_login_log)

        if _login_errors:
            self._main_engine.close()
            self._event_engine.stop()
            raise RuntimeError(f"网关 {self.gateway_name} 登录失败：{_login_errors[0]}")

        self._connected = True
        logger.info(f"[LiveAdapter] 已连接网关：{self.gateway_name}")

    def disconnect(self):
        """断开连接并释放资源。"""
        self._main_engine.close()
        self._event_engine.stop()
        self._connected = False
        logger.info(f"[LiveAdapter] 已断开网关：{self.gateway_name}")

    @staticmethod
    def _load_gateway(name: str):
        """动态加载 vn.py 网关类，支持常见网关名称。"""
        gateway_map = {
            "CTP": ("vnpy_ctp", "CtpGateway"),
            "XTP": ("vnpy_xtp", "XtpGateway"),
            "IB": ("vnpy_ib", "IbGateway"),
            "UFT": ("vnpy_uft", "UftGateway"),
        }
        if name not in gateway_map:
            raise ImportError(f"不支持的网关名称 '{name}'，可选：{list(gateway_map.keys())}")
        module_name, cls_name = gateway_map[name]
        import importlib

        mod = importlib.import_module(module_name)
        return getattr(mod, cls_name)

    # ──────────────────────────────────────────
    # 行情订阅（可选）
    # ──────────────────────────────────────────

    def subscribe(self, code: str, exchange: str | Exchange | None = None):
        """订阅合约行情（需网关支持 Md 接口）。"""
        resolved = normalize_exchange(code, exchange)
        req = SubscribeRequest(symbol=code, exchange=resolved)
        self._main_engine.subscribe(req, self.gateway_name)

    # ──────────────────────────────────────────
    # 与 acc_stats 兼容的核心接口
    # ──────────────────────────────────────────

    def get_position_by_code(self, code: str):
        """返回本地镜像持仓，与 acc_stats.get_position_by_code 接口一致。"""
        return self._mirror.get_position_by_code(code)

    def open_pos(
        self,
        code: str,
        price: float,
        direction: str,
        stop_loss: float,
        time: datetime,
        order_type: str = "LIMIT",
    ) -> bool:
        """
        开仓：向网关发送委托，并在 on_trade 回报后同步更新本地镜像。

        Parameters
        ----------
        order_type : str
            "LIMIT"（限价，默认）或 "MARKET"（市价）。
        """
        if not self._connected:
            logger.error("网关未连接，无法开仓。")
            return False

        resolved_exchange = normalize_exchange(code)
        req = OrderRequest(
            symbol=code,
            exchange=resolved_exchange,
            direction=_DIR_MAP[direction],
            type=OrderType.MARKET if order_type == "MARKET" else OrderType.LIMIT,
            volume=1,
            price=price,
            offset=_OFFSET_OPEN,
            reference="live_adapter_open",
        )
        vt_orderid = self._main_engine.send_order(req, self.gateway_name)
        if not vt_orderid:
            logger.error(f"[open_pos] 委托失败：{code} {direction} @{price}")
            return False

        with self._lock:
            self._pending_orders[vt_orderid] = (code, direction, "open", price, stop_loss, time)

        logger.info(f"[open_pos] 委托已发出 vt_orderid={vt_orderid} {code} {direction} @{price}")
        return True

    def close_pos(
        self,
        code: str,
        price: float,
        direction: str,
        target_trade,
        time: datetime,
        order_type: str = "LIMIT",
    ):
        """
        平仓：向网关发送委托，并在 on_trade 回报后同步更新本地镜像。
        target_trade 传入以保持与 acc_stats 接口一致（用于镜像账户更新）。
        """
        if not self._connected:
            logger.error("网关未连接，无法平仓。")
            return

        resolved_exchange = normalize_exchange(code)
        req = OrderRequest(
            symbol=code,
            exchange=resolved_exchange,
            direction=_DIR_MAP[direction],
            type=OrderType.MARKET if order_type == "MARKET" else OrderType.LIMIT,
            volume=1,
            price=price,
            offset=_OFFSET_CLOSE,
            reference="live_adapter_close",
        )
        vt_orderid = self._main_engine.send_order(req, self.gateway_name)
        if not vt_orderid:
            logger.error(f"[close_pos] 委托失败：{code} {direction} @{price}")
            return

        with self._lock:
            self._pending_orders[vt_orderid] = (code, direction, "close", price, target_trade, time)

        logger.info(f"[close_pos] 委托已发出 vt_orderid={vt_orderid} {code} {direction} @{price}")

    def cancel_order(self, vt_orderid: str):
        """撤销委托。"""
        req = CancelRequest(orderid=vt_orderid.split(".")[1], gateway_name=self.gateway_name)
        self._main_engine.cancel_order(req, self.gateway_name)
        logger.info(f"[cancel_order] 撤单：{vt_orderid}")

    # ──────────────────────────────────────────
    # 回调注册（供外部监听）
    # ──────────────────────────────────────────

    def register_on_order(self, cb: Callable):
        """注册委托回报回调，参数为 vn.py OrderData。"""
        self._order_callbacks.append(cb)

    def register_on_trade(self, cb: Callable):
        """注册成交回报回调，参数为 vn.py TradeData。"""
        self._trade_callbacks.append(cb)

    # ──────────────────────────────────────────
    # 内部回报处理
    # ──────────────────────────────────────────

    def _on_order(self, event):
        order = event.data
        for cb in self._order_callbacks:
            try:
                cb(order)
            except Exception as e:
                logger.exception(f"[on_order] 回调异常: {e}")

    def _on_trade(self, event):
        """成交回报：更新本地镜像账户。"""
        trade = event.data
        vt_orderid = trade.vt_orderid

        with self._lock:
            info = self._pending_orders.pop(vt_orderid, None)

        if info is None:
            logger.warning(f"[on_trade] 未找到对应委托记录：{vt_orderid}")
        else:
            code, direction, action, price, *rest = info
            actual_price = trade.price  # 以实际成交价更新镜像
            time = trade.datetime or datetime.now()

            if action == "open":
                stop_loss, open_time = rest
                self._mirror.open_pos(code, actual_price, direction, stop_loss, time)
            elif action == "close":
                target_trade, close_time = rest
                self._mirror.close_pos(code, actual_price, direction, target_trade, close_time)

        self._trade_queue.put(trade)
        for cb in self._trade_callbacks:
            try:
                cb(trade)
            except Exception as e:
                logger.exception(f"[on_trade] 回调异常: {e}")

    # ──────────────────────────────────────────
    # 便捷属性（直接访问镜像账户统计）
    # ──────────────────────────────────────────

    @property
    def balance(self) -> float:
        return self._mirror.balance

    @property
    def funds(self) -> float:
        return self._mirror.funds

    @property
    def open_trade_items(self):
        return self._mirror.open_trade_items

    @property
    def close_trade_items(self):
        return self._mirror.close_trade_items

    def get_total_margin(self) -> float:
        return self._mirror.get_total_margin()

    def get_target_close_trade(self, code, direction):
        return self._mirror.get_target_close_trade(code, direction)


class LiveTrader:
    """
    事件驱动实盘交易循环。

    Parameters
    ----------
    adapter : LiveAdapter
        已实例化（无需已连接）的 LiveAdapter。
    code : str
        合约代码，如 "CU2506"。
    interval : str
        K 线周期，与项目其他地方一致（"1m"/"1h"/"d" 等）。
    strategy : str
        signals.py 中已注册的策略名称。
    strategy_cfg : dict
        策略参数，与 scripts/get_args.py 中的 config 格式一致。
    stop_loss : float
        止损参数（传给 open_pos）。
    shares : int
        每次开仓手数。
    warmup_bars : int
        信号函数需要的最少 K 线根数，未达到时不下单。
    order_type : str
        下单类型："LIMIT" 或 "MARKET"。
    """

    def __init__(
        self,
        adapter: "LiveAdapter",
        code: str,
        interval: str,
        strategy: str,
        strategy_cfg: dict,
        stop_loss: float,
        shares: int = 1,
        warmup_bars: int = 30,
        order_type: str = "LIMIT",
    ):
        self.adapter = adapter
        self.code = code
        self.interval = interval
        self.strategy_name = strategy
        self.strategy_cfg = strategy_cfg
        self.stop_loss = stop_loss
        self.shares = shares
        self.warmup_bars = warmup_bars
        self.order_type = order_type.upper()

        # 滚动 K 线缓冲区：列 open/high/low/close/settle/volume
        self._bar_buf: deque[dict] = deque()

        # 止损状态（与 simulation.py 保持一致）
        self._stop_loss_triggered = False
        self._origin_dir = None

        # vn.py BarGenerator：把 tick 合成指定周期的 bar
        # interval 映射：vn.py 以分钟数区分（日线用 callback 直接传入）
        self._bg = BarGenerator(self._on_bar, window=self._parse_window(interval))

        self._running = False

    # ──────────────────────────────────────────
    # 公开接口
    # ──────────────────────────────────────────

    def start(self):
        """
        订阅行情并进入事件循环，阻塞直到收到 SIGINT（Ctrl+C）。
        """
        # 注册 tick 回调到网关
        from vnpy.event import EVENT_TICK

        self.adapter._event_engine.register(EVENT_TICK, self._on_tick_event)

        # 订阅合约行情
        self.adapter.subscribe(self.code)

        self._running = True
        logger.info(f"[LiveTrader] 开始实盘交易 {self.code} 策略={self.strategy_name}")

        # 优雅退出：捕获 Ctrl+C
        def _stop(sig, frame):
            logger.info("[LiveTrader] 收到停止信号，退出...")
            self._running = False

        _signal.signal(_signal.SIGINT, _stop)

        while self._running:
            _time.sleep(1)

        logger.info("[LiveTrader] 实盘循环已结束。")

    def stop(self):
        """手动停止（适用于非阻塞场景）。"""
        self._running = False

    # ──────────────────────────────────────────
    # 内部：tick → bar
    # ──────────────────────────────────────────

    def _on_tick_event(self, event):
        tick = event.data
        if tick.symbol == self.code:
            self._bg.update_tick(tick)

    def _on_bar(self, bar):
        """BarGenerator 每合成一根完整 K 线时调用。"""
        # 追加到缓冲区
        self._bar_buf.append(
            {
                "datetime": bar.datetime,
                "open": bar.open_price,
                "high": bar.high_price,
                "low": bar.low_price,
                "close": bar.close_price,
                "settle": getattr(bar, "settle_price", bar.close_price),
                "volume": bar.volume,
            }
        )

        if len(self._bar_buf) < self.warmup_bars:
            logger.debug(f"[LiveTrader] 预热中 {len(self._bar_buf)}/{self.warmup_bars}")
            return

        self._process_bar(bar)

    # ──────────────────────────────────────────
    # 内部：信号计算 → 下单决策
    # ──────────────────────────────────────────

    def _process_bar(self, bar):
        """每根 bar 完成后：计算信号 → 止损检查 → 下单。"""
        from get_data import DataQuery, normalize_exchange, normalize_interval
        from signals import StrategyRegistry

        # 1. 用缓冲区构建 DataQuery（复用 from_price_df，不访问数据库）
        df = pd.DataFrame(list(self._bar_buf)).set_index("datetime")
        exchange = normalize_exchange(self.code)
        dq = DataQuery.from_price_df(
            df, self.code, exchange, normalize_interval(self.interval), target="close"
        )

        # 2. 计算信号（与回测完全相同的 API）
        strategy_obj = StrategyRegistry.get(self.strategy_name, dq, self.strategy_cfg)
        signal_series = strategy_obj.trade(direction=1)

        # 只取最新一根 bar 对应的信号
        latest_signal = signal_series.iloc[-1]
        bar_time = bar.datetime

        # 3. 止损检查（逻辑与 simulation.py 相同）
        sl_fired, sl_dir = self.adapter._mirror.do_stop_loss(
            bar_time,
            self.code,
            bar.open_price,
            bar.high_price,
            bar.low_price,
            bar.close_price,
        )
        if sl_fired:
            self._stop_loss_triggered = True
            self._origin_dir = sl_dir

        if pd.isna(latest_signal):
            return

        from core.simulation import signal2dir

        sig_dir = signal2dir(latest_signal)
        n, current_dir = self.adapter.get_position_by_code(self.code)

        # 4. 开仓
        if (
            current_dir is None
            and sig_dir
            and (not self._stop_loss_triggered or sig_dir != self._origin_dir)
        ):
            for _ in range(self.shares):
                ok = self.adapter.open_pos(
                    self.code,
                    bar.close_price,
                    sig_dir,
                    self.stop_loss,
                    bar_time,
                    order_type=self.order_type,
                )
                if not ok:
                    break
            else:
                self._stop_loss_triggered = False

        # 5. 持仓与信号不一致：先平仓
        elif current_dir and (sig_dir is None or current_dir != sig_dir):
            close_dir = "long" if current_dir == "short" else "short"
            for _ in range(n):
                target = self.adapter.get_target_close_trade(self.code, close_dir)
                self.adapter.close_pos(
                    self.code,
                    bar.close_price,
                    close_dir,
                    target,
                    bar_time,
                    order_type=self.order_type,
                )
            if sig_dir and (not self._stop_loss_triggered or sig_dir != self._origin_dir):
                for _ in range(self.shares):
                    ok = self.adapter.open_pos(
                        self.code,
                        bar.close_price,
                        sig_dir,
                        self.stop_loss,
                        bar_time,
                        order_type=self.order_type,
                    )
                    if not ok:
                        break
                else:
                    self._stop_loss_triggered = False

        logger.info(
            f"[LiveTrader] bar={bar_time} signal={latest_signal} "
            f"pos=({n},{current_dir}) equity={self.adapter.balance:.2f}"
        )

    # ──────────────────────────────────────────
    # 工具函数
    # ──────────────────────────────────────────

    @staticmethod
    def _parse_window(interval: str) -> int:
        """把 '1h'/'1m'/'d' 映射为 BarGenerator 的 window（分钟数）。"""
        interval = str(interval).lower().strip()
        mapping = {"d": 240, "w": 1200, "1h": 60, "1m": 1}
        if interval in mapping:
            return mapping[interval]
        # 处理 '5m' / '15m' 等
        if interval.endswith("m") and interval[:-1].isdigit():
            return int(interval[:-1])
        if interval.endswith("h") and interval[:-1].isdigit():
            return int(interval[:-1]) * 60
        return 1
