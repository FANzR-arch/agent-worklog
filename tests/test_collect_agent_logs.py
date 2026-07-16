import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "collect_agent_logs.py"
SPEC = importlib.util.spec_from_file_location("collect_agent_logs", SCRIPT)
worklog = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(worklog)


class AgentWorklogTests(unittest.TestCase):
    def test_default_redaction_masks_common_sensitive_values(self):
        raw = (
            r"联系 me@example.com，token=super-secret-value，"
            r"文件在 C:\Users\Alice Smith\project，密钥 sk-abcdefghijklmnop"
        )

        cleaned = worklog.clean_intent(raw)

        self.assertIn("[REDACTED_EMAIL]", cleaned)
        self.assertIn("token=[REDACTED_SECRET]", cleaned)
        self.assertIn("[REDACTED_SECRET]", cleaned)
        self.assertNotIn("Alice Smith", cleaned)
        self.assertNotIn("super-secret-value", cleaned)

    def test_redaction_can_be_disabled_explicitly(self):
        cleaned = worklog.clean_intent("token=super-secret-value", redact=False)

        self.assertEqual(cleaned, "token=super-secret-value")

    def test_codex_old_filename_does_not_hide_recent_message(self):
        recent = datetime.now().astimezone() - timedelta(hours=1)
        record = {
            "timestamp": recent.isoformat(),
            "type": "response_item",
            "payload": {
                "role": "user",
                "cwd": r"C:\Projects\demo",
                "content": [{"type": "input_text", "text": "继续昨天的发布修复"}],
            },
        }

        with tempfile.TemporaryDirectory() as tmp:
            old_home = worklog.HOME
            worklog.HOME = tmp
            try:
                path = (
                    Path(tmp)
                    / ".codex"
                    / "sessions"
                    / "2025"
                    / "01"
                    / "01"
                    / "rollout-2025-01-01T00-00-00-old-session.jsonl"
                )
                path.parent.mkdir(parents=True)
                path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")

                rows = list(worklog.adapter_codex(since_dt=recent - timedelta(days=1)))
            finally:
                worklog.HOME = old_home

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][1], "demo")
        self.assertEqual(rows[0][3], "继续昨天的发布修复")

    def test_intent_cap_keeps_newest_items_independent_of_scan_order(self):
        now = datetime.now().astimezone()

        def synthetic_adapter(since_dt=None):
            yield now - timedelta(hours=3), "demo", "s1", "最旧任务"
            yield now, "demo", "s1", "最新任务"
            yield now - timedelta(hours=1), "demo", "s1", "中间任务"

        old_adapters = worklog.ADAPTERS
        worklog.ADAPTERS = {"Synthetic": synthetic_adapter}
        try:
            buckets = worklog.collect("day", since_days=1, max_intents=2)
        finally:
            worklog.ADAPTERS = old_adapters

        key, _ = worklog.period_key(now, "day")
        intents = buckets[key]["src"]["Synthetic"]["intents"]
        self.assertEqual(intents, ["最新任务", "中间任务"])

    def test_totals_count_unique_sessions_across_periods(self):
        buckets = {
            "2026-07-15": {"src": {"Codex": {"sessions": {"s1", "s2"}, "count": 3}}},
            "2026-07-16": {"src": {"Codex": {"sessions": {"s2", "s3"}, "count": 2}}},
        }

        totals = worklog.aggregate_totals(buckets)

        self.assertEqual(totals["Codex"], (3, 5))


if __name__ == "__main__":
    unittest.main()
