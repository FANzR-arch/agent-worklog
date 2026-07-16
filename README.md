# agent-worklog

[![tests](https://github.com/FANzR-arch/agent-worklog/actions/workflows/test.yml/badge.svg)](https://github.com/FANzR-arch/agent-worklog/actions/workflows/test.yml)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-3776AB)](https://www.python.org/)
[![MIT License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

命令行里的 AI Agent 用得越多，越难回答一个简单问题：

> 我这周到底推进了什么？

`agent-worklog` 扫描本机现存的 Claude Code、Codex 和 Grok 对话日志，提取真实用户意图，
按日、周或月整理成 Markdown / JSON / CSV，再交给你选择的 Agent 生成工作记录。

- 本地采集器不联网，不修改原始日志
- 纯 Python 标准库，零第三方依赖
- 自动探测常见日志位置与系统本地时区
- 默认脱敏常见密钥、邮箱与用户目录
- 支持项目过滤、时间窗口和 Excel 友好的 CSV

## 它怎么工作

```text
本地 Agent 日志
    ↓ adapters
用户输入 + 时间 + 项目 + 会话
    ↓ 去噪 / 脱敏 / 去重 / 分桶
Markdown + JSON + CSV
    ↓ 可选：交给 AI 总结
日报 / 周报 / 月报
```

采集和总结是两层。脚本负责可验证的数据整理；“这周的三条主线是什么”仍由人或 AI 判断。

## 快速开始

需要 Python 3.9+。

```bash
git clone https://github.com/FANzR-arch/agent-worklog.git
cd agent-worklog

# 先看本机有哪些 Agent 日志，不读取内容
python scripts/collect_agent_logs.py --list-agents

# 近 7 天，按日整理
python scripts/collect_agent_logs.py --granularity day --since 7 --out ./out

# 近 4 周，按周整理
python scripts/collect_agent_logs.py --granularity week --since 28 --out ./out

# 近 3 个月，按月整理并输出 CSV
python scripts/collect_agent_logs.py --granularity month --since 90 --csv --out ./out

# 只看项目名中包含 philthink 的记录
python scripts/collect_agent_logs.py --granularity week --project philthink --out ./out
```

Windows 如果控制台中文乱码：

```powershell
$env:PYTHONUTF8='1'
python scripts\collect_agent_logs.py --granularity week --since 28 --out .\out
```

输出文件：

- `worklog-intents.<粒度>.md`：给人或 Agent 阅读的意图原料
- `worklog-intents.<粒度>.json`：结构化数据
- `worklog-summary.<粒度>.csv`：可选的周期 × Agent 汇总表

## 作为 Agent Skill 使用

整个仓库可以作为一个自包含 Skill：

- Claude Code：复制到项目 `.claude/skills/agent-worklog/` 或用户级 skills 目录
- Codex / Grok / 其他 Agent：复制到对应的 skills 目录
- 纯脚本用户：直接运行 `scripts/collect_agent_logs.py`

根目录的 [`SKILL.md`](SKILL.md) 定义了从采集、总结到报告交付的完整工作流。

## 支持的数据源

| Agent | 日志位置 | 状态 |
|---|---|---|
| Claude Code | `~/.claude/projects/*/*.jsonl` | 已解析 |
| Codex | `~/.codex/sessions/**`、`~/.codex/archived_sessions/**` | 已解析 |
| Grok | `~/.grok/sessions/<项目>/<会话>/chat_history.jsonl` | 已解析 |
| Gemini | `~/.gemini/antigravity/conversations/*.pb` | 仅检测 |
| Cursor | `~/.cursor` / workspaceStorage SQLite | 仅检测 |
| Qwen / Continue / Aider | 各自目录 | 仅检测 |

“仅检测”表示会出现在探测报告中，但目前不会读取对话内容。

## 隐私边界

采集脚本没有网络请求，默认会尝试遮盖：

- 常见 API token 与 Bearer token
- `token=...`、`password=...` 等凭证赋值
- 邮箱地址
- Windows、macOS 与 Linux 用户目录中的用户名

这只是尽力而为的脱敏。项目名、客户名、内部链接或业务内容仍可能进入结果。

更重要的是：如果把生成文件交给云端 AI 总结，文件内容会按该服务的隐私政策发送给模型提供商。
本地采集不等于本地总结。完整说明见 [`PRIVACY.md`](PRIVACY.md)。

确实需要原始内容时可以关闭脱敏：

```bash
python scripts/collect_agent_logs.py --granularity week --no-redact
```

## 已知边界

- 日志覆盖上限取决于各 Agent 当前还保留多少本地会话。
- 默认每个周期、每个来源保留最新 60 条去重意图，可用 `--max-intents` 调整。
- 会话数只能说明使用痕迹，不能直接等同于工作量。
- Grok 日志缺少逐条时间戳，因此整个会话按开始日期归档。
- ChatGPT 网页、Claude.ai、豆包等没有本地 CLI 日志的服务不在覆盖范围。
- 脱敏规则不可能识别所有私密业务信息，公开报告前必须人工检查。

## 扩展新 Agent

在 `scripts/collect_agent_logs.py` 中增加一个 adapter：

```python
def adapter_xxx(since_dt=None):
    yield (local_datetime, project_name, session_id, raw_user_text)
```

然后注册到 `ADAPTERS`。时区转换、脱敏、去重、分桶和输出都由公共流程处理。

贡献前请使用合成日志运行测试，不要把真实对话或报告提交进仓库：

```bash
python -m unittest discover -s tests -v
```

更多约定见 [`CONTRIBUTING.md`](CONTRIBUTING.md)。

## License

[MIT](LICENSE)
