import numpy as np
import pandas as pd

from get_data import DataQuery


class StrategyRegistry:
    _registry = {}

    @classmethod
    def register(cls, name):
        def decorator(strategy):
            cls._registry[name] = strategy
            return strategy

        return decorator

    @classmethod
    def get(cls, name, data, config: dict):
        strategy_cls = cls._registry[name]
        return strategy_cls(data, **config)


class TradeStrategy:
    def __init__(self, data_query: DataQuery, **config):
        self.config = config
        self.source_data = self._get_source_data(data_query)
        self.target = data_query.target_price

    def _generate_signal(
        self,
    ) -> pd.Series:
        raise NotImplementedError

    def _get_source_data(self, data_query: DataQuery):
        # 设置生成因子的价格序列
        return data_query.price[self.config.get("source", "no_source_name")]

    def trade(self, direction: int) -> pd.Series:
        signal = self._generate_signal()
        return signal * direction


@StrategyRegistry.register("ma")
class MovingAverage(TradeStrategy):
    def _generate_signal(
        self,
    ):
        lag = self.config.get("lag", "unknown")
        signal = np.sign(self.source_data - self.source_data.rolling(lag).mean().shift(1))
        signal = signal.reindex(self.target.index).shift(1).ffill()
        return signal


@StrategyRegistry.register("dma")
class DualMA(TradeStrategy):
    def _generate_signal(
        self,
    ):
        short, long = self.config.get("short", 5), self.config.get("long", 20)
        signal = np.sign(
            self.source_data.rolling(short).mean() - self.source_data.rolling(long).mean()
        )
        signal = signal.reindex(self.target.index).shift(1).ffill()
        return signal


@StrategyRegistry.register("mr")
class MeanReverse(TradeStrategy):
    def _generate_signal(
        self,
    ):
        lag, thr = self.config.get("lag", 50), self.config.get("threshold", 1)
        source_cp = self.source_data.to_frame(name="fac_value")
        source_cp["thr"] = (
            source_cp["fac_value"] - source_cp["fac_value"].rolling(lag).mean()
        ) / source_cp["fac_value"].rolling(lag).std()
        source_cp["signal"] = np.where(source_cp["thr"] > thr, -1, np.nan)
        source_cp["signal"] = np.where(source_cp["thr"] < -thr, 1, source_cp["signal"])
        source_cp["signal"] = np.where(
            source_cp["thr"] * source_cp["thr"].shift(1) < 0, 0, source_cp["signal"]
        )
        signal = source_cp["signal"].shift(1).ffill()
        return signal


@StrategyRegistry.register("mom")
class Momentum(TradeStrategy):
    def _generate_signal(
        self,
    ):
        lag = self.config.get("lag", 5)
        signal = np.sign(self.source_data - self.source_data.shift(lag))
        signal = signal.reindex(self.target.index).shift(1).ffill()
        return signal


@StrategyRegistry.register("qtl")
class Quantile(TradeStrategy):
    def _generate_signal(
        self,
    ):
        ubr, lbr = self.config.get("ubr", "unknown"), self.config.get("lbr", "unknown")
        source_cp = self.source_data.to_frame(name="fac_value")
        source_cp["signal"] = np.where(
            source_cp["fac_value"] > source_cp["fac_value"].expanding().quantile(ubr), 1, np.nan
        )
        source_cp["signal"] = np.where(
            source_cp["fac_value"] < source_cp["fac_value"].expanding().quantile(lbr),
            -1,
            source_cp["signal"],
        )
        signal = source_cp["signal"].reindex(self.target.index).shift(1).ffill()
        return signal


@StrategyRegistry.register("abs")
class AbsoluteValue(TradeStrategy):
    def _generate_signal(
        self,
    ):
        level = self.config.get("level", "unknown")
        signal = np.sign(self.source_data - level)
        signal = signal.reindex(self.target.index).shift(1).ffill()
        return signal


def get_signal(name: str, config: dict, data: DataQuery, direction: int = 1) -> pd.Series:
    strategy = StrategyRegistry.get(name, data, config)
    return strategy.trade(direction)
