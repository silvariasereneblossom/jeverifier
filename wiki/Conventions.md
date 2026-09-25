# JeVerifier wiki — conventions

This is the living wiki for **JeVerifier**. It lives in the repo (`docs/wiki/`) so docs move with the code in the same commits. The project's
existing docs stay where they are; the wiki links into them and adds overview pages, a doc map, session logs,
and consistency checks. Maintenance follows the protocols in `protocols/`.

## Layout

- `home.md` — front door; every page must be reachable from here (Protocol 6)
- `overview.md` — what the project is and how it fits together, in one page
- `map.md` — generated section map of the project's own docs (`jeverifier wiki map`)
- `sessions/` — `index.md` plus one Jev-triaged log per session (Protocol 5)
- `meta/` — style guide and how the AI-maintained wiki works
- `protocols/` — maintenance workflows, invoked as "run Protocol N"

## Conventions

- Relative Markdown links to `.md` files, with GitHub heading anchors for sections.
- The code and the project's check scripts are the source of truth; the wiki describes them.
- Pages end with a **Related pages** section.
- Commits follow the host repo's rules: authored by the owner only, no attribution trailer; push only when asked.
- Verification command for this project: `.venv\Scripts\python -m pytest -q`.
- **Public mirror.** This repo is private; the public repo [jeverifier](https://github.com/silvariasereneblossom/jeverifier)
  gets only what `publish.json` lists, via `jeverifier wiki publish . <public checkout>`: the source, and these pages
  on its GitHub Wiki (a GitHub Action copies them over). Session logs, the doc map and any page whose first line is
  `<!-- INTERNAL ONLY -->` never go out, and the publish refuses to write anything that names a private project.
  Public pages describe private projects only generically.

## Protocols

| # | Protocol | File |
|---|---|---|
| 1 | Harmonize: fix contradictions, anachronisms, tone | [1-harmonize.md](Protocol-1-Harmonize) |
| 2 | Spot-check: Jev-ranked review list + sampled pairs, verdicts recorded | [2-spot-check.md](Protocol-2-Spot-Check) |
| 3 | Verify a claim against code, data and checks | [3-verify.md](Protocol-3-Verify) |
| 4 | Recursive harmonize until nothing changes | [4-recursive-harmonize.md](Protocol-4-Recursive-Harmonize) |
| 5 | Session log from a Jev digest | [5-session-log.md](Protocol-5-Session-Log) |
| 6 | Homepage coverage: orphans and broken links | [6-homepage-coverage.md](Protocol-6-Homepage-Coverage) |
| 7 | Commit & ship | [7-commit-and-ship.md](Protocol-7-Commit-and-Ship) |
