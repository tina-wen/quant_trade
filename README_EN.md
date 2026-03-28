# Quant Trade: A Practical Futures Backtesting Framework

Quant Trade is a lightweight and extensible framework for futures strategy research.
It connects Tushare + MySQL + a modular backtesting engine so you can move from raw data to performance metrics quickly.

Chinese version: [README.md](./README.md)

## Highlights

- Decoupled architecture: strategy generation and trade simulation are separated.
- Built-in strategies: MA, DMA, Momentum, Quantile, Absolute Threshold, Mean Reversion.
- Data pipeline included: import from CSV or Tushare into local MySQL.
- Streamlit UI: convenient pages for data writing and backtest visualization.
- Performance analytics: annual return, Sharpe ratio, drawdown, win rate, and PnL ratio.

## Project Structure

```text
quant_trade/
|- app/                 # Streamlit pages
|- config/              # Database and exchange mapping config
|- core/                # Simulation engine and account statistics
|- scripts/             # CLI scripts and examples
|- tests/               # Unit/integration tests
|- get_data.py          # Data query entry
|- signals.py           # Strategy signal generation
`- vnpy_adaptor.py      # Database adapter
```

## Quick Start

### 1. Configure MySQL

```sql
CREATE DATABASE your_database;
CREATE USER 'your_user'@'localhost' IDENTIFIED BY 'your_password';
GRANT ALL PRIVILEGES ON your_database.* TO 'your_user'@'localhost';
FLUSH PRIVILEGES;
```

First copy the example config:

```bash
cp config/database_config.example.json config/database_config.json
```

Then edit your local config [config/database_config.json](./config/database_config.json):

```json
{
  "db_name": "your_database",
  "db_user": "your_user",
  "db_pwd": "your_password",
  "db_host": "localhost",
  "tushare_token": "your_tushare_token"
}
```

### 2. Install Dependencies with uv

```bash
uv sync
uv pip install -e .
```

Note: editable install is recommended so CLI scripts, Streamlit pages, and top-level modules share a consistent import path.

### 3. Run Tests

```bash
uv run pytest tests/
```

### 4. Run CLI Backtest Example

Linux/macOS:

```bash
uv run bash scripts/test.sh
```

Windows:

```bat
uv run scripts/test.bat
```

### 5. Launch Streamlit UI

```bash
uv run streamlit run app/HomePage.py
```

## Built-in Strategies

See [signals.py](./signals.py).

| Strategy | Parameters |
|----------|------------|
| `ma` | `--lag` |
| `dma` | `--short`, `--long` |
| `mom` | `--lag` |
| `qtl` | `--lbr`, `--ubr` |
| `abs` | `--level` |
| `mr` | `--lag`, `--threshold` |

## Backtest Flow

The diagram below maps to scripts/backtest_exec.py and explains the pipeline from data input to signal generation, trade execution, and performance outputs.

```mermaid
flowchart TB
  A[Start backtest<br/>scripts/backtest_exec.py] --> B[Create account<br/>acc_stats]
  B --> C[Load market data<br/>DataQuery]
  C --> D[Generate signals<br/>get_signal]
  D --> E[Build trade input<br/>TradeOrder]
  E --> F[Backtest loop<br/>trade_simulation.backtest]

  subgraph LOOP[Per-trading-day processing]
    F1[Stop-loss check<br/>do_stop_loss] --> F2[Open/close by signal<br/>open_pos / close_pos]
    F2 --> F3[Mark-to-market settlement<br/>MTM + record balance]
  end

  F --> F1
  F3 --> G[Performance stats<br/>calc_performances]
  G --> H[Outputs<br/>perf_dict + pnl]

  C -.-> X1[(price / target_price / trade_days)]
  D -.-> X2[(signal series)]
  F3 -.-> X3[(daily_balances)]
  F2 -.-> X4[(close_trade_items)]
  X3 --> G
  X4 --> G

  classDef s1 fill:#E8F1FF,stroke:#3B82F6,color:#0F172A;
  classDef s2 fill:#ECFDF5,stroke:#10B981,color:#0F172A;
  classDef s3 fill:#FFF7ED,stroke:#F59E0B,color:#0F172A;
  classDef s4 fill:#FFE4E6,stroke:#E11D48,color:#0F172A;
  classDef data fill:#FFFFFF,stroke:#94A3B8,stroke-dasharray:4 3,color:#334155;

  class A,B s1;
  class C,D,E s2;
  class F,F1,F2,F3 s4;
  class G,H s3;
  class X1,X2,X3,X4 data;
```

## Demo

- Data writing page: https://github.com/user-attachments/assets/f7a9627a-bb17-4336-8acd-0cdf18773ce8
- Backtest visualization page: https://github.com/user-attachments/assets/bc1632a8-0c85-4481-847b-8b63528709c3

## Roadmap

- [ ] Multi-symbol portfolio backtesting
- [ ] Automatic factor mining
- [ ] Research-paper strategy templates

## Contributing

Issues and PRs are welcome.

GitHub: https://github.com/tina-wen/quant_trade
