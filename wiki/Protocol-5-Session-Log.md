# Protocol 5: Session Log

Session logs prevent **wiki drift**, the gap between what was decided in conversation and what the
docs say. Each log is a Jev-triaged digest of the session: verbatim quotes of the decisions, your
standing preferences, open items and status changes, plus a short summary written by Claude.

## Trigger

"Run Protocol 5" or "log this session". Also run it as part of Protocol 7 when a session made decisions.

## Procedure

1. **Generate the digest:** `jeverifier wiki log <repo> <session-id|latest> --since <last log date>`.
   It writes `sessions/logs/YYYY-MM-DD-<slug>.md` and adds a row to `sessions/index.md`.
   Open items the current handover already resolves are set aside automatically.
2. **Write the summary** at the top of the new log (3–6 bullets): what changed, what was decided,
   what is next. The quotes below it are the evidence; do not paraphrase them.
3. **Propagate** each decision into the page it belongs to (design, architecture, handover). A
   decision recorded only in a log has not been documented yet.

## At the start of a session

Read `sessions/index.md` and the newest one or two logs, then ask `jeverifier ctx find <repo> "<task>"`
(or the `context_find` MCP tool) for the doc sections the task needs.
