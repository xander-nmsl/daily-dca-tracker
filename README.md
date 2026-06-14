# 📊 Daily DCA Tracker

每天自动模拟定投 **$10** 到 8 种资产，追踪平均成本和盈亏，通过 Telegram Bot 发送每日报告。

## 投资组合

| 代码 | 资产 | 类型 |
|------|------|------|
| BTC | Bitcoin 比特币 | 加密货币 |
| QQQ | Invesco QQQ Trust | 纳斯达克100 ETF |
| SPY | SPDR S&P 500 ETF | 标普500 ETF |
| GOOGL | Alphabet (Google) | 科技股 |
| HYPE | Hyperliquid (DEX) | DEX 代币 |
| GLD | SPDR Gold Trust | 黄金 ETF |
| BRK.B | Berkshire Hathaway | 伯克希尔哈撒韦 |
| MKL | Markel Insurance | 马克尔保险 |

## 工作原理

1. 每个工作日（周一至周五），GitHub Actions 自动运行脚本
2. 脚本获取每项资产的当前价格
3. 模拟购买 $10 的每项资产
4. 计算平均成本、当前市值和盈亏
5. 通过 Telegram Bot 发送报告到你的聊天
6. 交易数据保存在 `data/portfolio.json` 中

## 快速开始

### 1. 发送消息给 Bot

在 Telegram 中搜索 `@ninayulin_bot`，发送任意一条消息（例如 "hi"），这样 Bot 就能获取到你的 chat_id。

### 2. Fork 或克隆此仓库

```bash
git clone https://github.com/xander-nmsl/daily-dca-tracker.git
cd daily-dca-tracker
```

### 3. 设置 GitHub Secrets（可选）

Bot token 已内置在代码中。如需覆盖，在仓库的 **Settings → Secrets and variables → Actions** 中添加：

| Secret | 说明 |
|--------|------|
| `TELEGRAM_TOKEN` | Bot Token（已内置，可选覆盖） |
| `TELEGRAM_CHAT_ID` | 你的 Telegram chat_id（自动发现，可选覆盖） |

### 4. 手动测试

```bash
pip install -r requirements.txt
python main.py
```

首次运行时会自动从 Bot 的消息记录中发现你的 chat_id。

## 自动运行

GitHub Actions 会在每个工作日的 **UTC 14:00**（北京时间 22:00）自动运行。

你也可以在 Actions 页面手动触发 (`workflow_dispatch`)。

## 报告示例

```
📊 Daily DCA Report
2026-06-14 14:00 UTC

Asset    Shares      Avg$      Now$      P&L$     P&L%
----------------------------------------------------------------
BTC      0.000155   64383.21  68000.00    0.56     3.62
QQQ       0.02000     500.00    510.00    0.20     2.00
HYPE      1.500000      6.67      7.20    0.53     8.00
...
──────────────────────────────
💰 Total Cost:   $80.00
📦 Total Value:  $82.16
🟢 Total P&L:   +$2.16 (+2.70%)
📊 Total Trades: 8
```

## 数据存储

所有交易记录保存在 `data/portfolio.json`。

## 许可证

MIT
