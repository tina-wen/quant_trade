# ������ Quant Trade：灵活的期货策略回测框架

一个支持多种策略、支持 tushare 接入的期货回测系统。只需一个 tushare token 和本地 MySQL，即可快速开始。
> ������ English version: [README_EN.md](./README_EN.md)
---

## ������ 项目亮点

- ������ **策略与回测解耦**：只需提供策略信号或交易指令即可回测，无需暴露策略源码。
- ������ **支持基本面数据**：任意时间序列数据均可用于生成信号。
- ������️ **本地数据库管理**：数据增删改查便捷高效，内置可视化接口。
- ������ **完整交易日志**：记录每一笔交易与账户变化，方便调试与复盘。
- ������ **策略绩效评估**：支持年化收益率、夏普比率、最大回撤、胜率、盈亏比等指标。

---

## ������ 支持策略（详见 `signals.py`）

| 策略名称 | 参数说明 |
|----------|----------|
| ma       | 滞后期：`--lag` |
| dma      | 短均线、长均线：`--short`, `--long` |
| mom      | 动量滞后期：`--lag` |
| qtl      | 分位区间：`--lbr`, `--ubr` |
| abs      | 固定阈值：`--level` |
| mr       | 均值回归滞后期、标准差阈值：`--lag`, `--threshold` |

---

## ������️ 安装与配置

### 1. 安装依赖

建议 **不使用 pip 安装 vnpy**，请手动 clone 编译：

```bash
git clone https://github.com/vnpy/vnpy.git
# 修改 install.sh 删除 ta-lib 安装部分
# 修改 pyproject.toml 删除 ta-lib 依赖
bash install.sh
```

安装 ta-lib：

```bash
conda install -c conda-forge ta-lib
```

### 2. 设置 MySQL 数据库

```sql
CREATE DATABASE your_database;
CREATE USER 'your_user'@'localhost' IDENTIFIED BY 'your_password';
GRANT ALL PRIVILEGES ON your_database.* TO 'your_user'@'localhost';
FLUSH PRIVILEGES;
```

配置文件（放于 `./quant_trade/database_config.json`）：

```json
{
  "db_name": "your_database",
  "db_user": "your_user",
  "db_pwd": "your_password",
  "db_host": "localhost",
  "tushare_token": "your_tushare_token"
}
```

---

## ������ 快速开始

### 下载并写入行情数据

```python
from ts_download import save_csv_bar, save_ts_bar, save_ts_contr
from vnpy.trader.constant import Exchange, Interval

save_csv_bar("datasets/price.csv", "Unnamed: 0", "test", Exchange.DCE, Interval.DAILY)
save_ts_contr("CU1911", Exchange.SHFE, datetime(2018,10,1), datetime(2019,12,1))
save_ts_bar("CU1911", Exchange.SHFE, datetime(2018,10,1), datetime(2019,12,1), Interval.DAILY)
```

### 数据验证（MySQL）

```sql
SHOW TABLES;
SELECT * FROM dbbardata WHERE symbol = 'CU1911';
SELECT * FROM dbcontractdata WHERE symbol = 'CU1911';
```

### 一键回测

```bash
python backtest_exec.py   --code CU1911   --start_time 2018-12-15   --end_time 2019-06-16   --source close   --trade_strategy dma   --log_dir ./log/demo/CU1911_dma
```

---

## ������ 回测结果示例

```text
用户 demo 本次模拟的年化收益：-4.69%，夏普：-3.08，最大回撤：3.54%，胜率：33.33%，盈亏比：0.56
```

详细交易日志见 `./logs/账户名/合约_策略_时间.log`。

---

## ������ TODO

- [ ] 多合约组合回测
- [ ] 策略表现可视化
- [ ] 自动因子挖掘
- [ ] 嵌入研报策略

---

## ������ 参与贡献

这是业余选手造的轮子，欢迎 Issue / PR / Star！  
������ [项目地址](https://github.com/tina-wen/quant_trade)
