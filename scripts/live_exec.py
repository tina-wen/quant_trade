from config.loader import load_broker_settings
from core.live_adapter import LiveAdapter, LiveTrader


def main():
    gateway, settings = load_broker_settings()
    adapter = LiveAdapter(gateway, settings, init_funds=1_000_000, shares=1)
    trader = LiveTrader(
        adapter,
        code="CU2506",
        interval="1h",
        strategy="dma",  # signals.py 中注册的任意策略
        strategy_cfg={"short": 5, "long": 20, "source": "close"},
        stop_loss=0.05,
        warmup_bars=30,
    )
    adapter.connect()
    trader.start()  # 阻塞，Ctrl+C 优雅退出


if __name__ == "__main__":
    main()
