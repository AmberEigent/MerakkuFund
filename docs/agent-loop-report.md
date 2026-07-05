# Agent Loop 完整报告

> polyagents · Ask 侧 agent loop · 分支 `feat/agent-loop-kernel`
> 一句话:**在 Ask 界面发一句请求(找 alpha / 分析 / 推荐 / 回测 / 下纸面单),LLM 内核每步自动选能力、动手、出结果。**

---

## 1. 一图总览

```
浏览器 composer(选 mode / model / packs / skills)
        │  POST /api/chat  {messages, mode:"kernel", packs:[...]}
        ▼
web/server.py _stream_kernel ──► run_mode("kernel", packs)
        │                              │  registry = CORE + 选中的 vertical packs
        ▼                              ▼
  KernelController(LLM=DeepSeek)  ◄── registry_for("kernel", packs)
        │  每步:看请求+已收集facts+可用能力菜单 → 选一个能力 或 给最终答案
        ▼
   能力(capability).run(ctx) ──► 写回 facts ──► 下一步 … 直到 final
        │  (analyze/recommend/paper_trade 内部再调引擎子 agent)
        ▼
   _kernel_summary / 结构化渲染 ──► SSE 流回浏览器
```

**核心理念(mentor 的模型)**:一个内核 loop + 一个能力注册表。**常驻(CORE)能力**永远在;**垂直能力**打包成 **packs**,**选中才临时加载**。controller 用 LLM 每步动态选,不写死流水线。

---

## 2. 三层架构

| 层 | 是什么 | 文件 |
|---|---|---|
| **模式(mode)** | Ask 的入口:`kernel`(默认,内核 loop)/ `domain` / `general` / `auto`(旧 ReAct 路由) | `web/server.py::_stream` |
| **内核 loop** | `KernelController`:LLM 驱动,每步选能力或答话;确定性反向链 planner 作离线兜底 | `kernel/controller.py`、`kernel/core.py` |
| **能力 + 子 agent** | 20 个 capability(precond/effect + run);部分内部调引擎的 signal/decision/reflection 子 agent | `kernel/capabilities.py`、`kernel/wiring.py`、`agents/` |

**能力单元** = `Capability{ name, description, preconditions, effects, run(ctx)→facts }`。controller 只从"前置条件已满足"的能力里选;加新能力 = 声明 precond/effect + 注册,**不动 loop 主干**。

---

## 3. 请求全流程(一次 kernel 请求)

1. **composer** 组装 `{messages, model, mode:"kernel", packs:[选中的垂直包], skills:[选中的SKILL.md]}` → `POST /api/chat`。
2. `chat()` → `_stream(...packs)` → `_stream_kernel(history, session, packs)`。
3. `run_mode("kernel", request, history, packs)`:
   - `registry_for("kernel", packs)` = **CORE + 选中 packs 的能力**(packs=None→全加载;[]→只核心)。
   - 建 `KernelController(registry, DeepSeek)`。
4. **controller 循环**(最多 8 步):
   - `_decide`:把 `请求 + 已收集 facts + 当前可运行能力菜单 + 对话历史` 交给 DeepSeek → 返回 `{"action":"call","capability":X}` 或 `{"action":"final","answer":...}`。
   - 选中能力 → `cap.run(ctx)` → 结果并进 `ctx.facts` → 下一步。
   - 能力可 `stream(ctx, emit)`:内层 token/工具调用**实时流出**(如 domain_answer 的 ReAct agent)。
   - 能力报错 → 写进 scratchpad,让模型**重规划**(不崩)。
5. **渲染**:`_kernel_summary(ctx)` 按 facts 里的结构化产出选一个专用渲染器(见 §6),流回浏览器。
6. **跨轮记忆**:prior turns 进 prompt,能解析"上一条那个市场"。
7. **LLM 不可用兜底**:退回确定性反向链 `AgentLoop`(离线可跑)。

---

## 4. 能力全表(20 个 = 10 常驻 + 10 垂直)

> 已做一波筛选:删掉 `strategy`(被 analyze_market 完全取代)、并把 `data_agent`/`backtest_agent`(kernel 里被 batch_backtest 覆盖)移出 kernel 菜单(仍供 research/lab 模式用)。菜单更精简 → controller 选得更准。

### 常驻(CORE · loading=auto · 永远在)

| 能力 | 触发意图 | 产出 |
|---|---|---|
| `hunt_alpha` | "找 alpha / 扫机会 / 现在值得关注什么" | crypto 错价 + 微结构资金流 汇总机会板 |
| `scan_markets` | 批量扫活跃市场 | market_batch |
| `resolve_market` | 把请求解析到一个具体市场(含"最活跃的") | market_ref |
| `analyze_market` | 分析/评估一个市场 | 五段框架(探索→推理→数据→回溯→结论) |
| `discover_markets` | 给主题/事件找候选市场 | candidates |
| `recommend_markets` | 主题→推荐标的 | 推荐+排序(+ market_ref) |
| `evaluate_skill` | "我们有没有 alpha / 校准报告 / 跑赢市场没" | Brier/ECE/baseline 报告 |
| `portfolio_review` | "看我的组合 / P&L / 持仓" | 纸面组合 + P&L + 归因 |
| `langgraph_answer` | 通用问答 / 概念 / 编码(带 web 搜索) | answer |
| `domain_answer` | 市场只读工具问答(scan/orderbook/evaluate) | answer |

### 垂直(loading=select · 选中对应 pack 才加载)

| Pack | 能力 | 触发意图 |
|---|---|---|
| **backtest-lab** | `batch_collect` | 批量采集 L1 入库 |
| | `batch_backtest` | 单策略·某领域批量回测 |
| | `backtest_strategies` | 多策略对比(某领域) |
| | `backtest_matrix` | **策略 × 领域** 全扫矩阵 |
| | `promotion_gate` | Lab 晋级门:够不够 paper-ready |
| **crypto-arb** | `find_crypto_arb` | crypto 现货 vs 隐含概率错价 |
| **microstructure** | `microstructure_scan` | 跨市场订单簿/资金流扫描 |
| **news-events** | `news_sentiment` | 新闻+情绪(需 TAVILY_API_KEY) |
| **paper-exec**(gated) | `paper_trade` | size+风控+下纸面单 |
| | `settle_and_reflect` | 结算+Layer4 反思写 lesson |

---

## 5. 子 agent 调用流程(引擎内部)

`analyze_market` / `recommend_markets` / `paper_trade` 内部都调 `engine.analyze(market)`,它跑一条 **LangGraph 分析图**(L1+L2 三个子 agent):

```
engine.analyze(market)
  ├─ L1 数据采集(确定性,无 LLM)
  │    价格/成交量/订单簿微结构/交易流 → 因子向量(features.py)
  ├─ signal_agent   (LLM=DeepSeek, 结构化输出)   → p_true + 方向 + 理由
  ├─ decision_agent (确定性数学)                 → 校准 p_true → edge → 分数-Kelly → 风控门 → buy/hold/sell + size
  └─ reflection_agent(LLM=DeepSeek, 结构化输出)  → 风险 flag / 蛛丝马迹 / OOD
```

- **signal_agent**:从因子/flow/情绪估 `p_true`(LLM 推理,带 RAG 相似市场 + Layer4 lessons)。
- **decision_agent**:**不是 LLM**——先把 p_true 向市场价校准,再 `edge=p_cal−price`,分数-Kelly,硬风控门(流动性/点差/6% edge floor/时间年化 APY)。
- **reflection_agent**:LLM 事前自省(风险、假设、分布外)。

`paper_trade` 在此之上:若 decision 是 buy/sell → `paper_execute`(walk order book 真实滑点 + 熔断器 CircuitBreaker)→ 更新纸面组合。
`settle_and_reflect`:市场结算后 → 结算 payout + `reflect_on_outcome`(LLM 出 Lesson)→ 注入未来 signal。

跨 provider 结构化输出:`llm.py::structured_output` 强制 `function_calling`,让 DeepSeek 也能出结构化(它不支持 json_schema)。

---

## 6. 各能力链的触发流程(意图 → 路径)

| 用户意图 | loop 路径 | 渲染 |
|---|---|---|
| 分析某个/最活跃市场 | `resolve_market → analyze_market` | 五段框架 |
| 主题 → 推荐标的 | `discover_markets → recommend_markets`(→可选 analyze_market 深挖) | 推荐+候选排序 |
| 找 alpha / 扫机会 | `hunt_alpha`(内部并 find_crypto_arb + 微结构扫) | 机会板 |
| crypto 套利 | `find_crypto_arb` | 终端型错价表 + 触碰型分列 |
| 微结构/资金流 | `microstructure_scan` | flow 排序表 |
| 新闻/情绪 | `news_sentiment` | 新闻+情绪表 |
| 批量采数据 | `scan_markets → batch_collect` | 采集计数 |
| 单/多策略回测 | `batch_backtest` / `backtest_strategies` | 对比表 |
| 策略×领域全扫 | `backtest_matrix` | 2D 矩阵 |
| 够不够 paper | `promotion_gate` | 四门表 |
| 纸面下单 | `resolve_market → paper_trade` | 交易结果+组合 |
| 结算+学习 | `settle_and_reflect` | 结算表+lessons |
| 看组合 / 有没有 skill | `portfolio_review` / `evaluate_skill` | 组合 / 校准报告 |
| 概念/编码/外部 | `langgraph_answer` / `domain_answer` | 文本 |

**完整交易学习闭环**:
```
hunt_alpha(找) → analyze_market(深挖) → paper_trade(动手)
    → settle_and_reflect(结算+反思) → evaluate_skill(验证) → lesson 回喂 signal
```

---

## 7. 垂直包 & 选择加载机制(mentor 的"临时加载=选择")

- **CORE**:10 个常驻能力,任何请求都能自动选。
- **PACKS**:5 个垂直包(backtest-lab / crypto-arb / microstructure / news-events / paper-exec),`registry_for("kernel", packs)` 决定加载哪些:
  - `packs=None`(默认)→ 全部加载(向后兼容)。
  - `packs=[]` → 只核心。
  - `packs=["crypto-arb"]` → 核心 + 只 crypto-arb。
- composer 的 **Skills 选择器**列出所有 `loading=select` 的项(垂直包 + SKILL.md 工作流),勾选 → 传 `packs` 进 loop。
- **统一格式**:`/api/library` 把一切表示成 skill:`kind`(capability/pack/workflow)+ `loading`(auto/select)。Library 页面据此分"常驻/自动"和"垂直/选中"两栏。
- **实测**:`packs:[]` + crypto 请求 → 用不了 find_crypto_arb(核心兜底);`packs:["crypto-arb"]` → 能用。**选择真的控制加载。**

---

## 8. 现在这个 web 能做什么

### 视图(左栏)
| 区 | 视图 | 能干什么 |
|---|---|---|
| modes | **Ask** | 聊天:kernel 内核 loop(默认)/ domain / general |
| | **Lab** | 假设 / 策略 / 回测(同事负责的模块) |
| | **Live** | 实盘(gated,默认关) + MCP + 审计 |
| library | **Capabilities** | **统一 Skills 一览**:常驻能力 + 垂直包 + SKILL.md(带 kind/loading 徽章) |
| | **Markets** | 实时 Polymarket 行情(按 24h 量) |
| | **Objects** | 5 类金融对象 + 3 道晋级门状态机 |
| | **Evaluation** | 校准/技能报告 |

### composer(输入区)
- **mode** 选择器(Kernel 默认 / Auto / Domain / General)
- **model** 选择器(实际走 DeepSeek,见 .env)
- **Skills** 选择器(统一:垂直包 + 工作流,勾选控制 loop 加载)
- 附件上传(文本/图片/PDF)

### API 端点
- **聊天**:`POST /api/chat`(SSE 流:token/tool/tool_result/done/error)
- **清单**:`/api/library`(统一)、`/api/capabilities`、`/api/packs`、`/api/skills`、`/api/mcp`
- **数据**:`/api/markets`、`/api/portfolio`、`/api/evaluation`、`/api/backtest`(qlib)、`/api/backtest_replay`
- **Lab**:`/api/lab/hypotheses`、`.../backtests`、`/api/lab/reports/{id}`、`/api/lab/system/status`
- **对象**:`/api/objects`、`.../alpha_test`、`.../promote`
- **其它**:`/api/strategy`(多智能体 SSE)、`/api/audit`、`/api/upload`

---

## 9. 数据 / 引擎分层(能力底下的料)

| 层 | 内容 | 模块 |
|---|---|---|
| **L1 数据** | Gamma/CLOB 行情、订单簿微结构、成交流、K 线、因子向量、RAG | `dataflows/`、`storage/db.py`(SQLite) |
| **L2 决策** | signal(LLM p_true)→ decision(确定性 Kelly/风控)→ reflection(LLM 自省) | `agents/` |
| **L3 执行** | Paper/Live 执行端口 + 熔断器 + 组合 | `execution/` |
| **L4 反馈** | 结算 payout + 反思 Lesson + 注入未来 signal | `feedback/` |
| **评估** | Brier/log-loss/ECE vs 市场 baseline + 晋级门 | `evaluation/` |
| **策略库** | naive/momentum/mean_reversion/favorite_longshot/trend_strength/volume_momentum | `strategies/library.py` |
| **云端 DB** | SQLAlchemy 双后端(SQLite dev / Postgres prod),objects+audit 已迁 | `storage/engine.py`、`tables.py` |

---

## 10. 诚实性 & 边界(经得起追问)

**诚实表现**:
- 大多回测/分析结论是 **HOLD / 无 alpha / 未达门槛**——不虚报 edge(预测市场大体有效)。
- crypto 套利只对**终端型**市场评分,**触碰型**分列不评(避免模型伪影)。
- backtest_matrix 里偶现的 ✅ 都标了"小样本/技术信号,真 edge 更可能在别处"。
- 不迎合("一定夺冠"→仍给真实低概率)、不对没分析的市场编数字。
- news 无 key、无结算交易等 → **优雅提示**,不报错不瞎编。
- **报错兜底**:domain_answer/answer 的 ReAct 工具 agent 在 DeepSeek 上偶发畸形工具调用(400 "bad parameter"),已加 `_plain_answer` **无工具回退**——失败就退到纯 LLM 作答,不把 API 错误冒给用户。

**已知边界**:
- LLM 走 **DeepSeek**(Anthropic key 组织被禁的临时方案);其工具调用不如 Claude 稳,故上面的兜底。
- **真正的 alpha 源仍窄**:技术信号打不赢市场,edge 更可能在 microstructure/crypto 套利/事件。
- **news 情绪用词典打分**(中文/含蓄读不准),建议换 LLM scorer。
- **#10 monitor 未做**:持续/定时无人值守监控(需调度+watchlist)——"真自动化"的最后一块。
- 实盘 Live 关闭;paper 交易 gated;云端 Postgres 只迁了 objects+audit(市场数据仍 SQLite)。

---

## 11. 现状

- **loop:20 能力(10 常驻 + 10 垂直,5 个包)**,LLM=DeepSeek,全在 `feat/agent-loop-kernel`。
  (筛选后:删了 `strategy`、`data_agent`、`backtest_agent`、`strategy-supervisor` 包 —— 冗余,被 analyze_market/batch_backtest 覆盖。)
- 上次的"欠缺 skills 名单"做完 **9/10**,只剩 #10 monitor(调度)。
- 全能力验证 **18 测试 · 16/18 自动 PASS → 复核后 17-18/18 达标**(见 `agent-loop-test-answers.md`)。
- 测试 **~291 passed**;能力都有对应 `tests/test_kernel_*.py`。
- 四份文档:`agent-loop-report.md`(本报告)/ `-test-suite.md`(题库)/ `-test-results.md`(判定)/ `-test-answers.md`(全能力验证+完整回答+评估)。

**下一步候选**:#10 monitor(watchlist+调度,真无人值守)· news 换 LLM scorer · 云端 DB 部署(需运维权限)· Ask→Lab 的 propose_hypothesis(和同事对齐)· backtest_strategies/matrix 合并。
