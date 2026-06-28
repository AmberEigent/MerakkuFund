# 贡献指南（CONTRIBUTING）

感谢参与 AIHF / polyagents！本文件规定分支、Issue、PR 的协作规范，所有贡献者请遵守。

---

## 一、分支规范约定

### 统一分支命名规则

| 类型 | 前缀 | 用途 | 示例 |
|---|---|---|---|
| 功能 | `feat/` | 新功能 / 新模块 | `feat/ask-upload-mvp` |
| 修复 | `fix/` | bug 修复 | `fix/ask-readonly-tool-surface` |
| 重构 | `refactor/` | 优化 / 重构（不改变外部行为） | `refactor/decision-agent-kelly` |
| 热更 | `hotfix/` | 线上紧急热修复 | `hotfix/circuit-breaker-bypass` |

分支名用小写 + 短横线分隔，语义清晰，避免 `my-branch`、`test1` 这类无意义命名。

### 硬性规则

- **所有修改禁止直接在 `main` 开发**。`main` 受保护，历史所有改动均经 PR 合入。
- 必须：从最新 `main` 切出新分支 → 开发 → 提 PR → 评审通过 → 合并主干。
- 合并后**立即删除功能分支**，保持仓库整洁（远程 `main` + 长期分支只保留必要者）。

```bash
# 切分支前先同步 main
git checkout main
git pull --ff-only

# 切出功能分支
git checkout -b feat/ask-upload-mvp

# ...开发、提交...
git push -u origin feat/ask-upload-mvp
```

---

## 二、Issue 任务分配

### 1. 新建 Issue

- 描述需求 / bug：背景、预期行为、复现步骤（bug 类）、验收标准。
- 添加标签：`feat` / `bug` / `docs`（必要时加 `refactor`、`urgent` 等）。
- 大功能先在 `docs/product/` 写或更新 PRD，再（或同时）建 Issue 引用之。本项目遵循**先 PRD 后代码**（ask、lab 模块均如此）。

### 2. 分配与去重

- **右侧 Assignees 指定负责人**，避免多人重复开发同一任务。认领前先看 Issue 是否已被 assign。
- **Milestone 绑定版本**，统一迭代节奏（如 `v0.2`）。

### 3. 关联

- PR 描述里写明关联 Issue（`Closes #N` / `Relates #N`），合并时自动关闭对应工单。

---

## 三、PR 标准流程

### 1. 开发

1. 从最新 `main` 切出新分支（见上文）。
2. 代码放对应模块目录（见 README「Layout」）。新工具 / agent 遵循项目的 **port + adapter** 模式：定义协议/接口，默认实现可注入（参考 `Scorer`、`Forecaster`、`ExecutionClient`、`llm=`）。
3. **测试驱动**：在 `tests/` 加测试，项目偏好契约测试（参考 `test_lab_api_contract.py`）。测试必须**无 key、无网络**即可跑通——用 fake LLM / paper 模式，不引入真实 API 依赖。
4. 文档同步：设计改动更新 `docs/design/DESIGN.md`（token / 视觉语言），进度更新 `docs/planning/`。

### 2. 本地验证（提 PR 前必须通过）

```bash
python -m pytest                 # 全绿
python -m polyagents.web         # 前端改动需起服务目测
```

- 不得提交破坏测试的代码。
- 前端 / UI 改动务必本地目测，不要只靠测试。

### 3. 提交规范（Conventional Commits）

每个提交遵守约定式提交，scope 用模块名：

```
feat(ask): emergent Hypothesis — agent proposes, user Promotes (gate 1)
fix(ask): enforce read-only tool surface (PRD §二/§八-B)
docs(ask): Ask module PRD + dark hi-fi prototype
chore: reorganize docs, add Docker deployment
refactor(execution): extract Kelly sizing into risk.py
```

- 类型：`feat` / `fix` / `docs` / `chore` / `refactor` / `test`。
- scope：模块名，如 `ask` / `lab` / `web` / `runtime` / `execution` / `evaluation`。
- 多个小提交，每个聚焦一个关注点；引用 PRD 章节如有（`PRD §八-B`）。
- **一个 PR 一个关注点**，不要混入无关的重排 / 重命名。

### 4. 提交 PR

完成后提交 PR，**必须填写**：

- **修改内容**：做了什么、为什么。
- **测试步骤**：如何验证（pytest 输出、目测步骤等）。
- **关联 Issue**：`Closes #N`，合并自动关闭对应工单。
- **不做的事**：明确边界，避免评审误解。

### 5. 评审与合并

- 在 PR 右侧 **Reviewers 指定 1 位同事评审**（目前统一指定 **@Andywchao**）。
- 评审通过、CI 通过后合并。
- 合并后**删除功能分支**（本地 + 远程）：

```bash
git checkout main && git pull --ff-only
git branch -d feat/ask-upload-mvp           # 删本地
git push origin --delete feat/ask-upload-mvp # 删远程
```

---

## 四、项目特定约定

为避免踩坑，以下几点与本仓库强相关：

### 提交信息与 scope

历史提交统一用约定式提交 + 模块 scope（见上文）。请保持一致。

### 文档分层（`docs/README.md`）

| 目录 | 用途 |
|---|---|
| `docs/product/` | PRD（功能先于此处定义） |
| `docs/design/` | `DESIGN.md` 设计语言 + token；UI 行为说明 |
| `docs/planning/` | 进度、待决策、评审反馈 |
| `docs/prototypes/` | 原型稿 |
| `docs/architecture/` | 架构说明 |
| `docs/archive/` | 已废弃版本 |

### `.gitignore` 的特殊点

- 本地策略 / 方案文档被忽略：`*方案*.md`、`Merakku-AI-Hedge-Fund-*.md`。
- 但 `docs/**/*.md` 例外保留——**私有笔记别进仓库，正式文档放 `docs/`**。

### 安全边界（不可破坏）

- **执行层默认 paper**：`execution_mode="paper"`，live 执行需显式开启 + `POLYMARKET_PRIVATE_KEY`，且永不作为默认。
- **工具面默认只读**：Ask 等模式默认只读不下单（见 `fix(ask): enforce read-only tool surface`）。
- **密钥走环境变量**：`ANTHROPIC_API_KEY`、`POLYMARKET_PRIVATE_KEY`、`TAVILY_API_KEY` 等不提交。`.env` 已被忽略。

### 设计 token

- `docs/design/DESIGN.md` 是视觉设计语言单一来源。
- 前端 token 改动须同步 `DESIGN.md`。避免引入与既有 token 体系冲突的硬编码颜色。

---

## 五、快速 checklist

提 PR 前自查：

- [ ] 从最新 `main` 切出，分支名符合 `feat/` `fix/` `refactor/` `hotfix/` 规范
- [ ] 未直接动 `main`
- [ ] `python -m pytest` 全绿
- [ ] 前端改动已本地目测
- [ ] 提交信息符合 Conventional Commits + 模块 scope
- [ ] PR 填写：修改内容、测试步骤、关联 Issue（`Closes #N`）
- [ ] PR 指定 Reviewer（@Andywchao）
- [ ] 无密钥 / 私有笔记误提交
- [ ] 文档同步（PRD / DESIGN.md / planning 如涉及）

---

## 六、本地环境

```bash
# 安装依赖
python -m pip install -r requirements.txt

# 跑测试（根目录即可，pytest.ini 已配 pythonpath=. ）
python -m pytest

# 起前端（需 ANTHROPIC_API_KEY）
python -m polyagents.web        # http://127.0.0.1:8000
```

数据层（Gamma / 行情 / 盘口）为公开只读接口，无需 key；`TAVILY_API_KEY` 可选（启用新闻采集）。
