# agent-worklog

把散落在多个命令行 AI Agent 里的对话记录，全量扫出来、去噪、按 **日 / 周 / 月** 汇总成一张
**工作记录表**。回答「我到底做了什么」，适合写日报 / 周报 / 月报，也适合自我复盘。

- 只读本地日志，**数据不出本机**
- 纯 Python 标准库，**零依赖**
- 自动探测日志位置 + 系统本地时区，**换机器/换人即可用**

---

## 快速使用

```bash
# 近 7 天，按日
python scripts/collect_agent_logs.py --granularity day --since 7 --out ./out

# 近 4 周，按周
python scripts/collect_agent_logs.py --granularity week --since 28 --out ./out

# 近 3 个月，按月
python scripts/collect_agent_logs.py --granularity month --since 90 --out ./out

# 只统计某个项目（项目名含关键词，不区分大小写）
python scripts/collect_agent_logs.py --granularity week --project myproject

# 额外导出汇总表 CSV（utf-8-sig，Excel/飞书直接打开中文不乱码）
python scripts/collect_agent_logs.py --granularity month --csv

# 只看本机装了哪些 Agent、各有多少会话（不采集）
python scripts/collect_agent_logs.py --list-agents
```

生成 `out/worklog-intents.<粒度>.md`（可读原料）与同名 `.json`。
脚本只做**扫描 + 去噪 + 分桶**；把原料**总结成表**由 AI Agent 完成（见根 `SKILL.md` 的 Workflow）。

> Windows 若中文乱码/报错：命令前加 `PYTHONUTF8=1`（PowerShell：`$env:PYTHONUTF8=1;` 再执行）。
> 需要 Python 3.7+。

---

## 支持的数据源

| Agent | 日志位置 | 状态 |
|---|---|---|
| Claude Code | `~/.claude/projects/*/*.jsonl` | ✅ |
| Codex | `~/.codex/sessions/**`、`~/.codex/archived_sessions/**` | ✅ |
| Grok | `~/.grok/sessions/<项目>/<会话>/chat_history.jsonl` | ✅ |
| Gemini | `~/.gemini/antigravity/conversations/*.pb` | 🔍 仅检测（protobuf 二进制）|
| Cursor | `~/.cursor` / workspaceStorage 的 SQLite | 🔍 仅检测 |
| Qwen / Continue / Aider | 各自目录 | 🔍 仅检测 |

「仅检测」= 会在探测报告里列出，但暂不解析其内容。

---

## 分享给别人怎么做

整个 `agent-worklog/` 目录自包含，拷贝即用：

- **Claude Code**：放进对方的 `.claude/skills/agent-worklog/`（项目级）或 `~/.claude/skills/`（全局）。
- **Codex / Grok / 其它 Agent**：把目录放到对方约定的 skills 位置；核心 `scripts/collect_agent_logs.py` 可独立运行，不依赖任何 Agent。
- **纯脚本用户**：只拷 `scripts/collect_agent_logs.py` 也能跑，`--list-agents` 先探测。

> ⚠️ **代码可以随便分享，报告不要**：脚本本身不含任何个人数据；但它**生成的工作记录**含真实项目名、文件路径、业务信息——发给别人前请自己先过一遍、删敏感项。

---

## 扩展一个新 Agent（给会改代码的人）

在 `scripts/collect_agent_logs.py` 里加一个 adapter 即可：

1. 写一个生成器 `def adapter_xxx(since_dt=None): yield (local_dt, project, session_id, raw_text)`
   - `local_dt`：本地时区 aware 时间（用 `parse_iso()` 解 ISO、`parse_ms()` 解毫秒时间戳）。
   - `raw_text`：该轮用户原始输入（噪音由公共 `clean_intent()` 统一过滤，不用自己滤）。
2. 注册到 `ADAPTERS = {..., "Xxx": adapter_xxx}`。
3. 数会话数的话，在 `_session_counts()` 里补一行（可选，让探测报告更准）。

时区、分桶（日/周/月）、去噪、输出全部走公共逻辑，adapter 只负责「把某个 Agent 的日志读成 (时间, 项目, 会话, 原文)」。

---

## 局限

- **会话数 ≠ 工作量**：Claude 的「轮次」含工具返回会偏高，汇总以会话数与内容为准。
- **日志保留窗口**：各 Agent 会轮换/清理旧会话，扫得到的上限 = 现存日志文件。
- **Grok 按会话开始日归属**：Grok 的 `chat_history.jsonl` 无逐条时间戳，整个会话记在开始那天（从会话 UUIDv7 解出）；跨天长会话会归到第一天。
- **网页 / App 版聊天**：ChatGPT 网页、Claude.ai、豆包 App、Grok 网页等本机无日志文件，不在覆盖范围，需手动补。
