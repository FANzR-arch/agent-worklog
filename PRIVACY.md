# Privacy model

`agent-worklog` reads local CLI-agent logs. Those logs can contain project names, paths,
customer information, prompts, source-code fragments, email addresses, and secrets.

## What stays local

The collector in `scripts/collect_agent_logs.py` uses only the Python standard library.
It does not contain network requests and it never edits the source logs.

## What may leave the machine

The generated Markdown and JSON files contain cleaned excerpts from real prompts. If you
ask a cloud-hosted AI service to summarize those files, their content is sent to that
service under its own privacy and retention policy. “Local collection” therefore does
not automatically mean “local summarization.”

## Default safeguards

- Common API-token formats, bearer tokens, credential assignments, email addresses, and
  user-home path segments are redacted before output.
- Redaction is best-effort, not a substitute for reviewing the report.
- `--no-redact` disables this protection and should be used only with trusted local data
  handling.
- Generated reports are ignored by the repository’s `.gitignore` patterns.

Before sharing a report, search it for customer names, internal URLs, credentials,
absolute paths, and unpublished business information.
