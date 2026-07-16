# Contributing

The project intentionally stays dependency-free. New adapters should only translate one
agent’s log format into:

```python
(local_datetime, project_name, session_id, raw_user_text)
```

Keep time filtering, redaction, deduplication, bucketing, and output formatting in the
shared pipeline.

## Development

```bash
python -m unittest discover -s tests -v
python scripts/collect_agent_logs.py --help
python scripts/collect_agent_logs.py --list-agents
```

Tests must use synthetic logs. Do not commit real conversation exports, generated
worklogs, access tokens, customer names, or local absolute paths.
