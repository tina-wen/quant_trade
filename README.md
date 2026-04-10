# Quant Trade：一个面向实战的期货回测框架

轻量、模块化、可扩展的期货回测项目。接入 Tushare 与本地 MySQL 后，可快速完成数据落库、信号生成、交易仿真与绩效评估。

English version: [README_EN.md](./README_EN.md)

## 特性

- 策略与回测引擎解耦：策略只负责生成信号，回测只负责执行和统计。
- 多策略内置：均线、双均线、动量、分位数、绝对阈值、均值回归。
- 数据链路完整：支持 CSV/Tushare 数据写入 MySQL。
- 可视化支持：基于 Streamlit 的参数配置与结果浏览页面。
- 指标完备：年化收益、夏普、回撤、胜率、盈亏比等。

## 项目结构

```text
quant_trade/
|- app/                 # Streamlit 页面
|- config/              # 数据库与交易所映射配置
|- core/                # 交易仿真与账户统计核心逻辑
|- scripts/             # 命令行脚本与示例
|- tests/               # 单元/集成测试
|- get_data.py          # 数据查询入口
|- signals.py           # 策略信号生成
`- vnpy_adaptor.py      # 数据库适配层
```

## 快速开始

### 1. 配置 MySQL

```sql
CREATE DATABASE your_database;
CREATE USER 'your_user'@'localhost' IDENTIFIED BY 'your_password';
GRANT ALL PRIVILEGES ON your_database.* TO 'your_user'@'localhost';
FLUSH PRIVILEGES;
```

先复制示例配置文件：

```bash
cp config/database_config.example.json config/database_config.json
```

再编辑本地配置 [config/database_config.json](./config/database_config.json)：

```json
{
  "db_name": "your_database",
  "db_user": "your_user",
  "db_pwd": "your_password",
  "db_host": "localhost",
  "tushare_token": "your_tushare_token"
}
```

### 2. 安装依赖（uv）

```bash
uv sync
uv pip install -e .
```

说明：推荐使用 editable 安装，便于统一命令行脚本、Streamlit 页面与顶层模块的导入路径。

### 3. 运行测试

```bash
uv run pytest tests/
```

### 4. 运行命令行回测示例

Linux/macOS:

```bash
uv run bash scripts/test.sh
```

Windows:

```bat
uv run scripts/test.bat
```

### 5. 启动可视化页面

```bash
uv run streamlit run app/HomePage.py
```

## 支持策略

详见 [signals.py](./signals.py)。

| 策略名称 | 参数说明 |
|----------|----------|
| `ma` | `--lag` |
| `dma` | `--short`, `--long` |
| `mom` | `--lag` |
| `qtl` | `--lbr`, `--ubr` |
| `abs` | `--level` |
| `mr` | `--lag`, `--threshold` |

## 回测流程（Backtest Flow）

下图对应 scripts/backtest_exec.py 的主流程，用来说明回测中“数据输入 -> 信号生成 -> 交易执行 -> 绩效输出”的链路。

```mermaid
flowchart TB
  A[启动回测<br/>scripts/backtest_exec.py] --> A1{数据来源}
  A1 -->|sim=true| B1[生成模拟K线<br/>fake_stream + DataQuery.from_price_df]
  A1 -->|sim=false| B2[加载历史数据<br/>DataQuery]
  B1 --> C[创建账户<br/>acc_stats]
  B2 --> C
  C --> D[生成信号<br/>get_signal]
  D --> E[封装报单<br/>TradeOrder]
  E --> F[进入 backtest 主循环]

  subgraph LOOP[逐bar处理 bar_times]
    F1[计算当前 bar_trade_date<br/>resolve_trade_date] --> F2[止损检查<br/>do_stop_loss]
    F2 --> F3[处理截至当前时点的待执行信号<br/>按时间顺序推进]
    F3 --> F4[按信号开平仓<br/>open_pos / close_pos]
    F4 --> F5{是否该交易日最后一根bar}
    F5 -->|是| F6[按交易日盯市结算<br/>MTM + 日度权益快照]
    F5 -->|否| F7[继续下一根bar]
  end

  F --> F1
  F6 --> G[绩效统计<br/>calc_performances]
  G --> H[输出<br/>perf_dict + pnl]

  B1 -.-> X0[(行情K线 / 交易日映射)]
  B2 -.-> X0
  D -.-> X2[(交易信号序列)]
  F6 -.-> X3[(日度账户权益记录)]
  F4 -.-> X4[(已平仓成交记录)]
  X0 --> F
  X3 --> G
  X4 --> G

  classDef s1 fill:#E8F1FF,stroke:#3B82F6,color:#0F172A;
  classDef s2 fill:#ECFDF5,stroke:#10B981,color:#0F172A;
  classDef s3 fill:#FFF7ED,stroke:#F59E0B,color:#0F172A;
  classDef s4 fill:#FFE4E6,stroke:#E11D48,color:#0F172A;
  classDef data fill:#FFFFFF,stroke:#94A3B8,stroke-dasharray:4 3,color:#334155;

  class A,A1,B1,B2 s1;
  class C,D,E s2;
  class F,F1,F2,F3,F4,F5,F6,F7 s4;
  class G,H s3;
  class X0,X2,X3,X4 data;
```

## 交易场景处理规则

- 止损检查：每根 bar 都执行一次 `do_stop_loss`；无持仓时函数内部直接返回。
- 空仓开仓：仅在信号非 0 且满足止损后再入场限制时尝试开仓。
- 反手信号：先按当前持仓手数全部平仓，再按目标手数尝试开新仓。
- 止损后同向限制：若当日触发过止损，会阻止同方向立即再开；只有一次完整开仓成功后才解除限制。
- 开仓失败处理：`open_pos` 返回 `False`（常见原因是保证金/手续费导致资金不足）时停止本次加仓尝试。
- 半仓策略：采用“当前 break 语义”，即允许部分成交（例如目标 3 手实际仅开成 1~2 手），后续按实际持仓手数平仓。

## 演示

- 数据写入页面：https://github.com/user-attachments/assets/f7a9627a-bb17-4336-8acd-0cdf18773ce8
- 回测可视化页面：https://github.com/user-attachments/assets/bc1632a8-0c85-4481-847b-8b63528709c3

## Roadmap

- [ ] 多合约组合回测
- [ ] 自动因子挖掘
- [ ] 研报策略模板化接入

## 贡献

欢迎提 Issue / PR / Star。

项目地址：https://github.com/tina-wen/quant_trade

## 常见问题（Troubleshooting）

### 1. 时区比较报错

- 现象：`TypeError: can't compare offset-naive and offset-aware datetimes`
- 原因：行情时间（可能带时区）与交易时段窗口（本地无时区时间）直接比较。
- 处理：在 `get_data.py` 中统一归一化时间（先转本地交易时区，再去除时区信息）。

### 2. 夜盘跨日导致交易日归属变化

- 夜盘品种（如铜）在凌晨的 bar 时间可能归属前一交易日的夜盘。
- 以 `resolve_trade_date` 的映射结果为准，再进行止损/结算/绩效计算。

### 3. 结算信息缺失

- 现象：`no settlement data found for YYYY-MM-DD`
- 原因：合约信息表在目标交易日缺失记录。
- 处理：优先查当日，若缺失则回退到最近可用日（lookback 窗口）继续计算。
