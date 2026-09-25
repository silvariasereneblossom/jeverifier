# {name} wiki — conventions

This is the living wiki for **{name}**. It lives in the repo (`docs/wiki/`) so docs move with the code in the same commits. The project's
existing docs stay where they are; the wiki links into them and adds overview pages, a doc map, session logs,
and consistency checks. Maintenance follows the protocols in `protocols/`.

## Layout

- `home.md` — front door; every page must be reachable from here (Protocol 6)
- `overview.md` — what the project is and how it fits together, in one page
- `map.md` — generated section map of the project's own docs (`jevauto wiki map`)
- `sessions/` — `index.md` plus one Jev-triaged log per session (Protocol 5)
- `checks/` — review verdicts, the accepted baseline (`wiki check`/`accept`), and `lint.json`: semantic code rules Jev checks per function (`jevauto wiki lint`)
- `meta/` — style guide and how the AI-maintained wiki works
- `protocols/` — maintenance workflows, invoked as "run Protocol N"

## Conventions

- Relative Markdown links to `.md` files, with GitHub heading anchors for sections.
- The code and the project's check scripts are the source of truth; the wiki describes them.
- Pages end with a **Related pages** section.
- Commits follow the host repo's rules: authored by the owner only, no attribution trailer; push only when asked.
- Verification command for this project: {check}.

## Protocols

| # | Protocol | File |
|---|---|---|
| 1 | Harmonize: fix contradictions, anachronisms, tone | [1-harmonize.md](protocols/1-harmonize.md) |
| 2 | Spot-check: Jev-ranked review list + sampled pairs, verdicts recorded | [2-spot-check.md](protocols/2-spot-check.md) |
| 3 | Verify a claim against code, data and checks | [3-verify.md](protocols/3-verify.md) |
| 4 | Recursive harmonize until nothing changes | [4-recursive-harmonize.md](protocols/4-recursive-harmonize.md) |
| 5 | Session log from a Jev digest | [5-session-log.md](protocols/5-session-log.md) |
| 6 | Homepage coverage: orphans and broken links | [6-homepage-coverage.md](protocols/6-homepage-coverage.md) |
| 7 | Commit & ship | [7-commit-and-ship.md](protocols/7-commit-and-ship.md) |
