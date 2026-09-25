# Protocol 7: Commit & Ship

## Trigger

"Run Protocol 7", "commit the wiki", or the end of a session that changed docs.

## Procedure

1. **Coverage:** run Protocol 6 and fix what it reports.
2. **Session log:** if the session made decisions, run Protocol 5 first.
3. **Map refresh:** `jevauto wiki map <repo>` if the project's docs gained, lost or renamed sections.
4. **Commit** following the host repository's rules (its `CLAUDE.md`): authored by the owner only,
   **no `Co-Authored-By` or other attribution**, with a message saying what changed in the docs.
   Keep wiki-only commits separate from code commits unless the docs describe that same change.
5. **Push only when the owner asks.** The repositories are private and single-owner; there is no
   pull-request step.
