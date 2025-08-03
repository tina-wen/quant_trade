#  Quant Trade：五分钟开始第一个期货回测

一个支持多种策略、支持 tushare 接入的期货回测系统。只需一个 tushare token 和本地 MySQL，即可快速开始。
>  English version: [README_EN.md](./README_EN.md)

---

## 项目亮点

-  **策略与回测解耦**：只需提供策略信号或交易指令即可回测，无需暴露策略源码。
-  **支持基本面数据**：任意时间序列数据均可用于生成信号。
-  **本地数据库管理**：数据增删改查便捷高效，内置可视化接口。
-  **完整交易日志**：记录每一笔交易与账户变化，方便调试与复盘。
-  **策略绩效评估**：支持年化收益率、夏普比率、最大回撤、胜率、盈亏比等指标。

---

##  支持策略（详见 `signals.py`）

| 策略名称 | 参数说明 |
|----------|----------|
| ma       | 滞后期：`--lag` |
| dma      | 短均线、长均线：`--short`, `--long` |
| mom      | 动量滞后期：`--lag` |
| qtl      | 分位区间：`--lbr`, `--ubr` |
| abs      | 固定阈值：`--level` |
| mr       | 均值回归滞后期、标准差阈值：`--lag`, `--threshold` |

---

## 设置 MySQL 数据库

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

##  快速开始

### 终端执行

```bash
streamlit run app/HomePage.py
```

### 写入本地MySQL
https://github.com/user-attachments/assets/f7a9627a-bb17-4336-8acd-0cdf18773ce8

##  回测结果可视化


https://github.com/user-attachments/assets/bc1632a8-0c85-4481-847b-8b63528709c3


---


##  TODO

- [ ] 多合约组合回测
- [ ] 自动因子挖掘
- [ ] 嵌入研报策略

---

##  参与贡献

业余选手造的轮子，欢迎 Issue / PR / Star！  
 [项目地址](https://github.com/tina-wen/quant_trade)
