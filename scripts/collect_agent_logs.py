#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
agent-worklog · 跨-Agent 对话日志采集器（可移植 / 可分享）

全量扫描本机各命令行 AI Agent 的对话记录，抽取真实用户意图，
按 日 / 周 / 月 分桶，导出为 JSON + 可读 Markdown，供 Agent 写成工作记录表。

设计原则（保证分享出去在别人机器上能跑）：
  - 只用 ~ (家目录) 相对路径自动探测，不硬编码任何用户名/绝对路径
  - 自动使用系统本地时区，不硬编码时区偏移
  - 只读本地日志文件，任何数据都不外传
  - 找不到某个 Agent 就跳过并报告，不报错

已支持（格式已验证）：Claude Code、Codex、Grok
仅检测不解析：Gemini(.pb 二进制)、Cursor(SQLite)、Qwen 等 —— 会在报告里列出

用法：
  python collect_agent_logs.py --granularity day   --since 7   --out .
  python collect_agent_logs.py --granularity week  --since 28  --out .
  python collect_agent_logs.py --granularity month --since 90  --out .
  python collect_agent_logs.py --list-agents          # 只探测，不采集
"""
import argparse, glob, json, os, re, sys, urllib.parse
from datetime import datetime, timezone, timedelta
from collections import defaultdict

HOME = os.path.expanduser("~")

# ---------------------------------------------------------------- 时间工具（本地时区）
def to_local(dt_utc_or_naive):
    """把 aware(UTC) 或 naive 时间统一转成本地 aware 时间。"""
    if dt_utc_or_naive.tzinfo is None:
        dt_utc_or_naive = dt_utc_or_naive.replace(tzinfo=timezone.utc)
    return dt_utc_or_naive.astimezone()  # 无参 = 系统本地时区

def parse_iso(s):
    try:
        return to_local(datetime.fromisoformat(str(s).replace("Z", "+00:00")))
    except Exception:
        return None

def parse_ms(ms):
    try:
        return datetime.fromtimestamp(int(ms) / 1000).astimezone()
    except Exception:
        return None

def period_key(dt, granularity):
    """返回 (排序键, 显示标签)。"""
    if granularity == "day":
        k = dt.strftime("%Y-%m-%d");  return k, k
    if granularity == "week":
        iso = dt.isocalendar()
        monday = dt - timedelta(days=dt.weekday())
        sunday = monday + timedelta(days=6)
        return f"{iso[0]}-W{iso[1]:02d}", f"{iso[0]}-W{iso[1]:02d} ({monday:%m-%d}~{sunday:%m-%d})"
    if granularity == "month":
        k = dt.strftime("%Y-%m");  return k, k
    raise ValueError(granularity)

# ---------------------------------------------------------------- 噪音过滤
BAD_PREFIX = ("<", "#", "base directory for this skill", "continue from where",
              "your tool call", "could not attach", "[request interrupted",
              "caveat:", "contents of", "the following", "you are ",
              "do you have an image", "use your image generation",
              "this session is being continued")
def clean_intent(text, cap=200):
    if not isinstance(text, str):
        return None
    t = text.split("<system-reminder>")[0].strip()
    t = re.sub(r"<environment_context>.*?</environment_context>", "", t, flags=re.S).strip()
    if not t:
        return None
    if t.lower().startswith(BAD_PREFIX):
        return None
    if t.startswith("[") and t.endswith("]") and len(t) < 60:
        return None
    t = " ".join(t.split())
    return t[:cap] if len(t) >= 4 else None

# 工具/临时目录名，不当作"项目"统计（通用，非个人特定）
PROJECT_DENY = {"scratchpad", "tmp", "temp", "out", "dist", "build",
                "node_modules", "agent-worklog"}
def basename(p):
    return os.path.basename(str(p).rstrip("\\/")) if p else None

def norm_project(p):
    b = basename(p)
    if not b:
        return None
    low = b.lower()
    if low in PROJECT_DENY or low.startswith(("_tmp", "tmp-", ".")):
        return None
    return b

def _cutoff(since_dt):
    """预筛下界：比窗口再早 1 天，避免时区边界误删。"""
    return None if since_dt is None else (since_dt - timedelta(days=1))

# ---------------------------------------------------------------- 各 Agent adapter
# 每个 adapter 是生成器，yield (local_dt, project, session_id, raw_text)
# since_dt 仅用于文件级快速预筛（可选），逐条日期仍由 collect() 精确过滤。

def adapter_claude(since_dt=None):
    cut = _cutoff(since_dt)
    for f in glob.glob(os.path.join(HOME, ".claude", "projects", "*", "*.jsonl")):
        if cut is not None:
            try:  # 文件最后修改时间早于窗口 → 内容全在窗口外，整文件跳过
                if datetime.fromtimestamp(os.path.getmtime(f)).astimezone() < cut:
                    continue
            except OSError:
                pass
        slug = basename(os.path.dirname(f))
        sid = os.path.splitext(os.path.basename(f))[0][:8]
        try:
            for line in open(f, encoding="utf-8"):
                try: d = json.loads(line)
                except Exception: continue
                if d.get("type") != "user":
                    continue
                dt = parse_iso(d.get("timestamp"))
                if dt is None:
                    continue
                proj = basename(d.get("cwd")) or slug
                c = d.get("message", {}).get("content")
                txt = c if isinstance(c, str) else None
                if isinstance(c, list):
                    for b in c:
                        if isinstance(b, dict) and b.get("type") == "text":
                            txt = b.get("text"); break
                yield dt, proj, sid, txt
        except Exception:
            continue

def _codex_fname_dt(path):
    m = re.search(r"(\d{4}-\d{2}-\d{2})T(\d{2})-(\d{2})-(\d{2})", os.path.basename(path))
    return parse_iso(f"{m.group(1)}T{m.group(2)}:{m.group(3)}:{m.group(4)}+00:00") if m else None

def adapter_codex(since_dt=None):
    files = glob.glob(os.path.join(HOME, ".codex", "sessions", "**", "*.jsonl"), recursive=True)
    files += glob.glob(os.path.join(HOME, ".codex", "archived_sessions", "**", "*.jsonl"), recursive=True)
    cut = _cutoff(since_dt)
    for f in files:
        if cut is not None:
            fdt = _codex_fname_dt(f)
            if fdt is not None and fdt < cut:      # 文件名日期早于窗口 → 整文件跳过
                continue
        sid = os.path.basename(f)[:40]; cwd = None
        try:
            for line in open(f, encoding="utf-8"):
                line = line.strip()
                if not line:
                    continue
                try: d = json.loads(line)
                except Exception: continue
                payload = d.get("payload") if isinstance(d.get("payload"), dict) else d
                if cwd is None:
                    m = re.search(r"<cwd>(.*?)</cwd>", line)
                    if m: cwd = basename(m.group(1))
                    elif isinstance(payload.get("cwd"), str): cwd = basename(payload["cwd"])
                if (payload.get("role") or d.get("role")) != "user":
                    continue
                dt = parse_iso(d.get("timestamp") or payload.get("timestamp"))
                if dt is None:
                    continue
                cont = payload.get("content"); txt = None
                if isinstance(cont, str):
                    txt = cont
                elif isinstance(cont, list):
                    for b in cont:
                        if isinstance(b, dict) and b.get("text"):
                            txt = b["text"]; break
                yield dt, cwd, sid, txt
        except Exception:
            continue

def _uuid7_ms(u):
    try:
        return datetime.fromtimestamp(int(u.replace("-", "")[:12], 16) / 1000).astimezone()
    except Exception:
        return None

def adapter_grok(since_dt=None):
    cut = _cutoff(since_dt)
    for f in glob.glob(os.path.join(HOME, ".grok", "sessions", "*", "*", "chat_history.jsonl")):
        parts = f.replace("\\", "/").split("/")
        proj = basename(urllib.parse.unquote(parts[-3])); uid = parts[-2]
        dt = _uuid7_ms(uid)
        if dt is None:
            try: dt = datetime.fromtimestamp(os.path.getmtime(f)).astimezone()
            except Exception: continue
        if cut is not None and dt < cut:           # 会话开始早于窗口 → 跳过
            continue
        try:
            for line in open(f, encoding="utf-8"):
                try: d = json.loads(line)
                except Exception: continue
                if (d.get("type") or d.get("role")) != "user":
                    continue
                cont = d.get("content")
                if isinstance(cont, list):
                    cont = " ".join(b.get("text", "") for b in cont if isinstance(b, dict))
                yield dt, proj, uid[:8], cont
        except Exception:
            continue

ADAPTERS = {"Claude": adapter_claude, "Codex": adapter_codex, "Grok": adapter_grok}

# 仅检测、暂不解析的 Agent（报告用）
DETECT_ONLY = {
    "Gemini": (os.path.join(HOME, ".gemini", "antigravity", "conversations"), "protobuf(.pb) 二进制，暂无解析"),
    "Cursor": (os.path.join(HOME, ".cursor"), "对话在 SQLite(state.vscdb)，路径复杂，暂未支持"),
    "Qwen":   (os.path.join(HOME, ".qwen"), "未发现对话日志"),
    "Continue": (os.path.join(HOME, ".continue"), "暂未支持"),
    "Aider":  (os.path.join(HOME, ".aider-desk"), "暂未支持"),
}

def _session_counts():
    """秒级：数会话文件数量，不解析内容。"""
    return {
        "Claude": len(glob.glob(os.path.join(HOME, ".claude", "projects", "*", "*.jsonl"))),
        "Codex": len(glob.glob(os.path.join(HOME, ".codex", "sessions", "**", "*.jsonl"), recursive=True))
                 + len(glob.glob(os.path.join(HOME, ".codex", "archived_sessions", "**", "*.jsonl"), recursive=True)),
        "Grok": len(glob.glob(os.path.join(HOME, ".grok", "sessions", "*", "*", "chat_history.jsonl"))),
    }

def detect():
    counts = _session_counts()
    found = [(n, counts[n]) for n in ADAPTERS if counts.get(n)]
    missing = [(n, 0) for n in ADAPTERS if not counts.get(n)]
    detect_only = [(name, note) for name, (path, note) in DETECT_ONLY.items() if os.path.exists(path)]
    return found, missing, detect_only

# ---------------------------------------------------------------- 采集主流程
def collect(granularity, since_days, max_intents, project_kw=None):
    since = datetime.now().astimezone() - timedelta(days=since_days)
    kw = project_kw.lower() if project_kw else None
    # key -> {label, source-> {intents, sessions:set, projects:set, count}}
    buckets = defaultdict(lambda: {"label": "", "src": defaultdict(
        lambda: {"intents": [], "sessions": set(), "projects": set(), "count": 0})})
    for src, fn in ADAPTERS.items():
        for dt, proj, sid, raw in fn(since_dt=since):
            if dt < since:
                continue
            if kw and kw not in str(proj or "").lower():
                continue
            key, label = period_key(dt, granularity)
            b = buckets[key]; b["label"] = label
            s = b["src"][src]
            s["count"] += 1
            if sid: s["sessions"].add(sid)
            np = norm_project(proj)
            if np: s["projects"].add(np)
            c = clean_intent(raw)
            if c and c not in s["intents"] and len(s["intents"]) < max_intents:
                s["intents"].append(c)
    return buckets

def to_json(buckets):
    out = {}
    for k in sorted(buckets, reverse=True):
        b = buckets[k]; out[k] = {"label": b["label"], "sources": {}}
        for src, s in b["src"].items():
            out[k]["sources"][src] = {
                "sessions": len(s["sessions"]), "user_msgs": s["count"],
                "projects": sorted(p for p in s["projects"] if p), "intents": s["intents"]}
    return out

def to_csv(buckets, path):
    """汇总表：每期×每源一行。utf-8-sig(BOM) 保证 Excel/飞书直接打开中文不乱码。"""
    import csv
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["period", "label", "source", "sessions", "user_msgs", "projects"])
        for k in sorted(buckets, reverse=True):
            b = buckets[k]
            for src in ADAPTERS:
                s = b["src"].get(src)
                if not s or not s["count"]:
                    continue
                w.writerow([k, b["label"], src, len(s["sessions"]), s["count"],
                            "; ".join(sorted(p for p in s["projects"] if p))])

def to_md(buckets, granularity):
    gl = {"day": "日", "week": "周", "month": "月"}[granularity]
    lines = [f"# 工作意图原料（按{gl}，本地时区，{datetime.now().astimezone():%Y-%m-%d %H:%M} 生成）",
             "", "> 供 Agent 据此写工作记录表。每条为过滤后的真实用户意图。", ""]
    for k in sorted(buckets, reverse=True):
        b = buckets[k]
        lines.append(f"\n## {b['label']}")
        for src in ADAPTERS:
            s = b["src"].get(src)
            if not s or not s["count"]:
                continue
            projs = ", ".join(sorted(p for p in s["projects"] if p)) or "—"
            lines.append(f"\n### {src} — {len(s['sessions'])}会话 / {s['count']}轮 / 项目: {projs}")
            for it in s["intents"]:
                lines.append(f"- {it}")
    return "\n".join(lines)

# ---------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser(description="跨-Agent 对话日志采集器")
    ap.add_argument("--granularity", choices=["day", "week", "month"], default="day")
    ap.add_argument("--since", type=int, default=None, help="回溯天数（默认 day=7/week=28/month=90）")
    ap.add_argument("--out", default=".", help="输出目录")
    ap.add_argument("--max-intents", type=int, default=60, help="每期每源最多保留意图数")
    ap.add_argument("--project", default=None, help="只统计项目名含此关键词的记录（不区分大小写）")
    ap.add_argument("--csv", action="store_true", help="额外导出汇总表 CSV（Excel/飞书可直接打开）")
    ap.add_argument("--list-agents", action="store_true", help="只探测各 Agent，不采集")
    args = ap.parse_args()
    try: sys.stdout.reconfigure(encoding="utf-8")   # Windows 控制台中文安全
    except Exception: pass

    found, missing, detect_only = detect()
    print("=== Agent 探测 ===")
    for n, c in found:   print(f"  [✓] {n:8s} {c} 个会话文件")
    for n, c in missing: print(f"  [ ] {n:8s} 无记录")
    for n, note in detect_only: print(f"  [!] {n:8s} 检测到但暂不支持（{note}）")
    if args.list_agents:
        return

    since = args.since if args.since is not None else {"day": 7, "week": 28, "month": 90}[args.granularity]
    buckets = collect(args.granularity, since, args.max_intents, project_kw=args.project)

    os.makedirs(args.out, exist_ok=True)
    base = os.path.join(args.out, f"worklog-intents.{args.granularity}")
    json.dump(to_json(buckets), open(base + ".json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    open(base + ".md", "w", encoding="utf-8").write(to_md(buckets, args.granularity))
    outputs = [base + ".md", base + ".json"]
    if args.csv:
        csv_path = os.path.join(args.out, f"worklog-summary.{args.granularity}.csv")
        to_csv(buckets, csv_path)
        outputs.append(csv_path)

    # 各源汇总
    totals = defaultdict(lambda: [0, 0])
    for b in buckets.values():
        for src, s in b["src"].items():
            totals[src][0] += len(s["sessions"]); totals[src][1] += s["count"]
    print(f"\n窗口: 近 {since} 天 | 粒度: {args.granularity} | 分组数: {len(buckets)}"
          + (f" | 项目过滤: {args.project}" if args.project else ""))
    for src in ADAPTERS:
        if src in totals:
            print(f"  {src:8s} {totals[src][0]:4d} 会话 / {totals[src][1]:5d} 轮")
    print("输出: " + "  ".join(outputs))

if __name__ == "__main__":
    main()
