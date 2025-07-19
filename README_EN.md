#  Quant Trade: A Flexible Futures Backtesting Framework

A modular and strategy-agnostic backtesting system for Chinese futures. With just a Tushare token and MySQL database, you can start backtesting your strategy in minutes.
>  中文版请见：[README.md](./README.md)


---

##  Highlights

-  **Strategy/Backtest Separation**: Cleanly decouples strategy generation from execution logic.
-  **Support for Fundamental Data**: Any time series can be used to generate trading signals.
-  **Local MySQL Management**: Structured, fast, and scalable data storage.
-  **Complete Trade Logs**: Every trade is recorded for transparency and debugging.
-  **Performance Metrics**: Annual return, Sharpe ratio, drawdown, win rate, and PnL ratio.

---

##  Built-in Strategies (`signals.py`)

| Strategy | Parameters |
|----------|------------|
| `ma`     | `--lag` |
| `dma`    | `--short`, `--long` |
| `mom`    | `--lag` |
| `qtl`    | `--lbr`, `--ubr` |
| `abs`    | `--level` |
| `mr`     | `--lag`, `--threshold` |

---

##  Installation & Configuration

### 1. Install Dependencies

It is recommended **not to install `vnpy` via pip**, but build it from source:

```bash
git clone https://github.com/vnpy/vnpy.git
# Edit install.sh: remove ta-lib installation
# Edit pyproject.toml: remove ta-lib dependency
bash install.sh
```

Install TA-Lib:

```bash
conda install -c conda-forge ta-lib
```

### 2. Set up MySQL

```sql
CREATE DATABASE your_database;
CREATE USER 'your_user'@'localhost' IDENTIFIED BY 'your_password';
GRANT ALL PRIVILEGES ON your_database.* TO 'your_user'@'localhost';
FLUSH PRIVILEGES;
```

Configuration file (`quant_trade/database_config.json`):

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

##  Quickstart

### Download and Save Bar Data

```python
from ts_download import save_csv_bar, save_ts_bar, save_ts_contr
from vnpy.trader.constant import Exchange, Interval

save_csv_bar("datasets/price.csv", "Unnamed: 0", "test", Exchange.DCE, Interval.DAILY)
save_ts_contr("CU1911", Exchange.SHFE, datetime(2018,10,1), datetime(2019,12,1))
save_ts_bar("CU1911", Exchange.SHFE, datetime(2018,10,1), datetime(2019,12,1), Interval.DAILY)
```

### Verify Data in MySQL

```sql
SHOW TABLES;
SELECT * FROM dbbardata WHERE symbol = 'CU1911';
SELECT * FROM dbcontractdata WHERE symbol = 'CU1911';
```

### Run Backtest

```bash
python backtest_exec.py   --code CU1911   --start_time 2018-12-15   --end_time 2019-06-16   --source close   --trade_strategy dma   --log_dir ./log/demo/CU1911_dma
```

---

##  Example Output

```text
Demo annualized return: -4.69%, Sharpe: -3.08, Max Drawdown: 3.54%, Win rate: 33.33%, PnL ratio: 0.56
```

Detailed logs at `./logs/{account}/{symbol_strategy_time}.log`

---

##  Roadmap

- [ ] Multi-symbol portfolio backtesting
- [ ] Strategy visualization tools
- [ ] Automatic factor mining
- [ ] Integration with published research

---

## Contributing

This is a personal weekend project — feel free to submit issues, PRs, or give it a ⭐.  
 [GitHub Project](https://github.com/tina-wen/quant_trade)
