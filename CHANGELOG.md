# Changelog

## 1.1.0 - 2026-07-16

- Keep recent messages from long-running Codex sessions even when the session filename is old.
- Sort intents by their real timestamps before applying `--max-intents`.
- Count unique sessions correctly across multiple reporting periods.
- Redact common secrets, email addresses, and user-home paths by default.
- Add `--no-redact`, `--version`, synthetic unit tests, and Windows/Linux CI.
- Clarify the privacy boundary between local collection and cloud-hosted summarization.

## 1.0.0 - 2026-07-14

- Initial Claude Code, Codex, and Grok log adapters.
- Day, week, and month grouping with Markdown, JSON, and CSV outputs.
