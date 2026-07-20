# Lab 实盘小额验证方案:Backtest → Monitor → Manual Ticket

> 一句话:用现有 Lab 回测体系先验证策略是否有历史证据,再用 dry-run monitor 扫当前流动性充足的 Polymarket 标的,
> 只在出现 **BUY/SELL 且 size > 0** 的 actionable signal 时人工小额执行,单笔不超过 **20 USDC**,
> 并通过 manual trade ticket 沉淀真实成交价、触发条件和收益归因。

---

## 1. 策略机制(为什么这样跑)

当前 Lab 的链路分成两段:

1. **Evidence Backtest**:回答“这个 strategy 在历史已结算样本上是否有证据支持”。
2. **Dry-run Monitor**:回答“现在活跃市场里是否存在满足同一 strategy 和风控门的交易候选”。

也就是说,backtest 不是直接下单器;它是先给 strategy 一个历史证据基础。monitor 也不是自动交易器;它只输出 dry-run 信号,
并明确 `action / p_cal / market_price / edge / APY / size_usdc`。

### 当前推荐策略

本轮小额验证优先使用:

- `momentum-v1`:跟随近期价格动量,并用轻量 flow 进行确认。

可选研究方向:

- `flow-imbalance-v1`:关注买卖成交流偏移。
- `microstructure-v1`:关注盘口压力、micro-price、spread。
- `contrarian-v1`:反动量/均值回归,适合观察但不建议第一笔真钱验证。

套利类机会当前已有 research scan 雏形,但还没有完全产品化到 Lab strategy registry 中。因此第一轮真钱验证建议先用
`momentum-v1` 做小额、可追踪的 live validation。

---

## 2. 系统功能支持(现在前端能看到什么)

入口:

```text
Lab → Backtest
```

### 2.1 Launch readiness

页面顶部的 **Launch readiness · system checks** 用于确认当前运行状态:

- DB backend:demo 阶段 SQLite 可用;生产应迁到 Postgres。
- News evidence:Tavily configured 时可补新闻特征。
- Execution:必须保持 `paper / dry-run`,避免自动真钱交易。
- Audit:记录 Lab API 关键事件。

### 2.2 Data ingestion

**Data ingestion · historical settled collections** 显示真实历史样本数量:

- `collections`:已写入 DataStore 的 historical collections。
- `usable settled`:可被 BacktestRunner 消费的已结算样本。

如果 usable settled 太少,先运行 ingestion,再做 backtest。

### 2.3 Strategy-aware evidence backtest

**Strategy-aware evidence backtest** 负责基于 Hypothesis 和 Strategy 生成 EvaluationReport。

重点看:

- `source = collections`
- `fixture = no`
- `PIT integrity = pass`
- `Brier Δ`
- `ECE`
- `condition clusters`

旧 report 可能没有 `condition clusters`;重新 Run evidence 后会带上新的 sample structure。

### 2.4 Dry-run monitor

**Dry-run monitor · active opportunities** 扫描当前活跃市场。

现在 UI 已区分:

- `actionable`:BUY/SELL 且 size > 0,才是可考虑人工下单的候选。
- `holds`:HOLD 诊断行,表示 edge 或风险门没有通过,不是下单建议。
- `shown`:当前展示的行数。

默认不展示 HOLD;只有勾选 `include holds` 才会展开诊断行。

### 2.5 Manual trade ticket

**Manual trade ticket · live validation log** 用于记录人工真钱验证:

- question
- token id
- side
- size
- entry price
- max entry
- report id
- Polymarket URL
- notes

Monitor 出现 BUY/SELL 行后,右侧会出现 `ticket` 按钮,可自动预填信号信息。保存后记录落到:

```text
storage/manual_trade_tickets/
```

---

## 3. 详细下单流程(mentor 执行)

### Step 1:准备 Hypothesis

进入 **Lab** 后选择一个已有 Hypothesis,或新建一个宽泛但和本轮验证相关的 Hypothesis:

```text
Momentum strategy can identify short-term mispriced liquid Polymarket sports markets.
```

当前 monitor 仍主要按 strategy 扫全市场,和 Hypothesis 的语义过滤还不强。因此 Hypothesis 主要用于绑定 evidence report 和后续归因。
后续应继续补 `hypothesis/category/query filter`。

### Step 2:运行 Evidence Backtest

进入:

```text
Lab → Backtest → Strategy-aware evidence backtest
```

设置:

```text
Hypothesis: 选择本轮验证 hypothesis
Strategy: momentum-v1
Category: all
```

点击:

```text
Run evidence
```

Review report 时只接受:

- source 是 `collections`
- fixture 是 `no`
- PIT clean
- 样本不是明显不足

如果 report 明显跑输市场,不进入真钱验证。

### Step 3:扫描当前机会

进入:

```text
Dry-run monitor · active opportunities
```

建议参数:

```text
Strategy: momentum-v1
Limit: 10 或 20
Min volume: 5000
Min edge: 0.05
Include holds: 不勾选
```

点击:

```text
Scan dry-run
```

只看 `actionable`:

- 若 `actionable = 0`,本轮没有建议下单。
- 若出现 BUY/SELL 且 size > 0,才进入下一步。

### Step 4:人工确认价格区间

对 BUY 信号,触发条件建议写成:

```text
BUY only if current price <= max_entry_price and edge remains positive.
```

示例:

```text
p_cal = 0.62
min_edge = 0.05
max_entry_price = 0.57
```

只有 Polymarket 实时页面价格仍然 `<= 0.57` 时,才允许人工买入。

如果 monitor 给出 HOLD:

```text
不下单。
```

如果价格已经超过 max entry:

```text
不追单。
```

### Step 5:人工下单

当前不启用自动真钱交易。mentor 在 Polymarket 页面手动执行:

```text
Size: 10 USDC
Hard cap: 20 USDC
```

建议第一轮只做一笔:

- 只选流动性充足标的。
- 不做薄盘口。
- 不在价格快速跳动时追单。

### Step 6:生成 Manual Trade Ticket

下单后回到 Lab 页面:

```text
Manual trade ticket · live validation log
```

如果 monitor 行右侧有 `ticket`,点击后自动预填。然后补:

- 实际成交价 `Entry price`
- Polymarket URL
- Report id
- Notes / screenshot path

点击:

```text
Save ticket
```

系统会检查:

- `size_usdc <= 20`
- `entry_price <= max_entry_price`
- `auto_execution = false`

保存后用于后续收益归因。

---

## 4. 如何判断这次是不是“可下单信号”

可以下单的最低条件:

| 检查项 | 要求 |
|---|---|
| action | BUY 或 SELL |
| size | > 0 且 <= 20 USDC |
| dry_run | true |
| edge | >= 5% |
| price | 未超过 max entry |
| liquidity | 充足 |
| backtest evidence | report 来自 real collections,不是 fixture |
| ticket | 下单后必须保存 |

不能下单的情况:

- `ACTION = HOLD`
- `SIZE = $0`
- `actionable = 0`
- 价格超过 max entry
- report 是 fixture fallback
- PIT warning 严重
- 手动无法记录 ticket

---

## 5. 诚实的风险与边界

1. **Dry-run 不是自动下单建议**:只有 BUY/SELL 且 size > 0 才是候选;HOLD 只是诊断。
2. **Monitor 与 Hypothesis 仍需加强绑定**:当前主要靠 strategy 扫全市场,后续要加 category/query/hypothesis filter。
3. **Edge 是研究信号,不是保证收益**:Polymarket 价格会快速变化,实际成交价可能让 edge 消失。
4. **小额验证无法证明长期有效**:10 USDC 是 live validation,不是统计显著性证明。
5. **套利模块未完全产品化**:套利可作为 research scan,但第一轮真钱验证建议用 momentum。
6. **人工执行有滑点和漏记风险**:必须用 trade ticket 记录实际成交信息。

---

## 6. 结论 / 下一步

当前系统已经具备小额实盘验证的最小闭环:

```text
Hypothesis → Evidence Backtest → Dry-run Monitor → Manual Execution → Trade Ticket
```

建议下一步:

1. 用 `momentum-v1` 先跑 1 笔 10 USDC live validation。
2. 严格只买 BUY/SELL actionable 行,不买 HOLD。
3. 下单后必须保存 manual trade ticket。
4. 结算或退出后回填 exit price / realized PnL。
5. 第二阶段再做:
   - monitor 按 hypothesis/category/query 过滤
   - ticket 列表页和 PnL 汇总
   - F1/NFL 等赛事专项 radar
   - 套利策略正式接入 Lab strategy registry

