import json
import os

# 读取并缓存配置
with open(os.path.join(os.path.dirname(__file__), "database_config.json"), "r") as f:
    DB_CONFIG = json.load(f)

with open(os.path.join(os.path.dirname(__file__), "exchange_map.json"), "r") as f:
    EXCHANGE_MAP = json.load(f)

with open(os.path.join(os.path.dirname(__file__), "trading_sessions.json"), "r") as f:
    TRADING_SESSION_CONFIG = json.load(f)
