import json
import os

# 读取并缓存配置
_cfg_dir = os.path.dirname(__file__)

with open(os.path.join(_cfg_dir, "database_config.json"), "r") as f:
    DB_CONFIG = json.load(f)

with open(os.path.join(_cfg_dir, "exchange_map.json"), "r") as f:
    EXCHANGE_MAP = json.load(f)

with open(os.path.join(_cfg_dir, "trading_sessions.json"), "r") as f:
    TRADING_SESSION_CONFIG = json.load(f)


def load_broker_settings() -> tuple[str, dict]:
    with open(os.path.join(_cfg_dir, "broker_config.json"), "r") as f:
        full = json.load(f)
    gateway = full.get("gateway", "").upper()
    settings: dict = {k: v for k, v in full[gateway].items() if not k.startswith("_")}
    return gateway, settings
