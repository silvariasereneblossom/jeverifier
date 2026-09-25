"""Command line: `jevauto keys …` to manage API keys, `jevauto ctx|wiki …` for docs, `jevauto run …` to automate."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import keys


def _keys(args: argparse.Namespace) -> int:
    if args.keys_cmd == "gui":
        from .keys_gui import main as gui

        gui()
    elif args.keys_cmd == "set":
        shown = keys.prompt_and_store(args.name, from_clipboard=args.clipboard)
        print(f"Stored {args.name} ({shown}) in Windows Credential Manager under '{keys.SERVICE}'.")
        if args.clipboard:
            print("Clipboard cleared.")
    elif args.keys_cmd == "import-env":
        for name in args.names or keys.names():
            print(f"{name}: {'imported' if keys.import_from_env(name) else 'not set in this environment'}")
    elif args.keys_cmd == "list":
        for name in keys.names():
            value = keys.get(name)
            print(f"{name}: {keys.masked(value) if value else '(not stored)'}")
    elif args.keys_cmd == "delete":
        print(f"{args.name}: {'deleted' if keys.delete(args.name) else 'was not stored'}")
    return 0


def _ctx(args: argparse.Namespace) -> int:
    from . import ctx

    out = Path(args.out) if args.out else ctx.OUT
    if args.ctx_cmd == "index":
        repo = Path(args.repo)
        print(f"wrote {ctx.write_index(repo, out / repo.resolve().name)}")
    elif args.ctx_cmd == "find":
        picked, total = ctx.find(Path(args.repo), args.task, budget_tokens=args.budget, always=tuple(args.always))
        print(ctx.render_reading_list(args.task, picked, total))
    elif args.ctx_cmd == "digest":
        transcript = ctx.resolve_transcript(args.session)
        body, stats = ctx.digest(transcript, since=args.since or "", handover=Path(args.handover) if args.handover else None)
        dest = out / "digests" / f"{transcript.stem[:8]}-{(args.since or 'all')[:10]}.md"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(body, encoding="utf-8", newline="\n")
        print(f"wrote {dest}  ({stats['turns']} turns ≈{ctx.tok(stats['turn_chars']):,} tok → digest ≈{ctx.tok(stats['digest_chars']):,} tok)")
    return 0


def _print_selftest(r: dict) -> None:
    for row in r["plants"]:
        scores = " ".join(f"{k}={row[k]}" for k in ("contra", "same", "number_same") if k in row)
        print(f"  [{row['type']}] {row['where']:<34} {row['change']:<26} general rank {row['rank'] or '-':<5} "
              f"number rank {row['number_rank'] or '-':<4} {row['why']}  {scores}")
        print(f"      planted: {row['planted_text'][:160]}")
        print(f"      partner: {row['partner']}: {row['partner_text'][:160]}")
    for kind, t in r["by_type"].items():
        print(f"{kind} plants: {t.get('candidates', 0)} candidates, {t.get('fair', 0)} judged fair; found {t['found']}/"
              f"{t['planted']} in the full lists (numbers top {r['top_numbers']}, general top {r['top']}); "
              f"{t['found_delta']}/{t['planted']} in delta mode")
    print(f"delta mode would list {r['delta_listed']} pairs for the planted edits; Jev ${r['cost_usd']}")


def _wiki(args: argparse.Namespace) -> int:
    from . import consistency, wiki

    repo = Path(args.repo)
    if args.wiki_cmd == "init":
        for p in wiki.init(repo, args.name or repo.resolve().name, args.summary or "", args.check_cmd):
            print(f"wrote {p}")
    elif args.wiki_cmd == "map":
        print(f"wrote {wiki.write_map(repo)}")
    elif args.wiki_cmd == "check":
        dest, stats = consistency.check(repo, top=args.top, max_cost=args.max_cost, deep=args.deep)
        print(f"review list: {dest}")
        if stats.get("mode") == "delta":
            print(f"delta: {stats['new_claims']} new or changed statements -> {stats['listed']} pairs to review")
        else:
            print("full ranking (first run or --deep); after reviewing, run: jevauto wiki accept <repo>")
        print(stats)
    elif args.wiki_cmd == "accept":
        path, info = consistency.accept(repo, git_ref=args.git_ref)
        print(f"accepted {info['claims']:,} statements as reviewed ({info['ref']}) -> {path}")
    elif args.wiki_cmd == "verdict":
        reports = sorted((consistency.core.OUT / repo.resolve().name).glob("consistency-*.md"))
        entry = consistency.record_verdict(repo, args.id, args.verdict, args.note or "", reports[-1] if reports else None)
        print(f"recorded {entry['verdict']} for {entry['id']} in docs/wiki/checks/verdicts.jsonl")
    elif args.wiki_cmd == "selftest":
        _print_selftest(consistency.selftest(repo, n=args.plants, top=args.top, max_cost=args.max_cost))
    elif args.wiki_cmd == "lint":
        from . import lint

        dest, stats = lint.lint(repo, max_cost=args.max_cost)
        print(f"lint report: {dest}\n{stats}")
    elif args.wiki_cmd == "publish":
        from .publish import publish

        print(f"{len(publish(repo, Path(args.dest)))} files in {args.dest}; review `git status` there before pushing")
    elif args.wiki_cmd == "log":
        print(f"wrote {wiki.log(repo, args.session, since=args.since or '', slug_text=args.slug)}")
    elif args.wiki_cmd == "coverage":
        orphans, broken = wiki.coverage(repo)
        print("orphan pages:", *(orphans or ["none"]), sep="\n  ")
        print("broken links:", *([f"{a} -> {b}" for a, b in broken] or ["none"]), sep="\n  ")
        return 1 if orphans or broken else 0
    return 0


def _run(args: argparse.Namespace) -> int:
    import os

    from . import jev

    try:
        provider = jev.choose()
    except RuntimeError as err:
        print(err, file=sys.stderr)
        return 2
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Missing ANTHROPIC_API_KEY for the built-in planner. Add it in the keys window "
              "(jevauto keys gui), or drive jevauto from Claude Code via its MCP server instead.",
              file=sys.stderr)
        return 2

    from .gate import JevGate
    from .planner import Hooks, Runner

    if args.window or args.launch:
        from .desktop import DesktopSurface

        surface = DesktopSurface(window=args.window, launch=args.launch)
        title = surface.window.window_text()
        if input(f"Attach to window {title!r}? Its contents will be sent to Claude and Jev "
                 "(secret-looking strings are masked). [y/N] ").strip().lower() != "y":
            return 1
    else:
        from .browser import BrowserSurface

        surface = BrowserSurface(headless=args.headless)
        if args.url:
            surface.navigate(args.url)

    hooks = Hooks(
        ask=lambda q: input(f"\n[claude asks] {q}\n> "),
        confirm=lambda d: input(f"\n[confirm irreversible action]\n    {d}\n  Proceed? [y/N] ").strip().lower() == "y",
        log=print,
    )
    try:
        print(f"Jev via {provider.name} ({args.jev_model or provider.model})")
        with jev.client(provider, model=args.jev_model) as jev_client:
            runner = Runner(surface, JevGate(jev_client), hooks, effort=args.effort, max_steps=args.max_steps)
            result = runner.run(args.task)
    finally:
        if not args.keep_open:
            surface.close()
    print(f"\n{'SUCCESS' if result.get('success') else 'NOT COMPLETED'}: {result.get('summary')}")
    print(f"trace: {runner.trace_path}")
    return 0 if result.get("success") else 1


def _wiki_parser(sub) -> None:
    w = sub.add_parser("wiki", help="living wiki in docs/wiki/ (IridescentCraft-style protocols)")
    ws = w.add_subparsers(dest="wiki_cmd", required=True)
    cost = {"type": float, "default": 1.0, "help": "stop before a run would spend more than this many USD"}
    wi = ws.add_parser("init", help="scaffold docs/wiki/ and point CLAUDE.md at it")
    wi.add_argument("repo")
    wi.add_argument("--name")
    wi.add_argument("--summary", help="one-paragraph description for the home page")
    wi.add_argument("--check-cmd", help="the project's verification command")
    ws.add_parser("map", help="regenerate map.md from the project docs").add_argument("repo")
    wc = ws.add_parser("check", help="Protocol 2: Jev-ranked contradiction pairs for Claude to review")
    wc.add_argument("repo")
    wc.add_argument("--top", type=int, default=130, help="pairs in the general review list")
    wc.add_argument("--deep", action="store_true", help="full ranking instead of only what changed since `accept`")
    wc.add_argument("--max-cost", **cost)
    wa = ws.add_parser("accept", help="record the current statements as reviewed; later checks show only changes")
    wa.add_argument("repo")
    wa.add_argument("--git-ref", help="accept the text as of this commit (e.g. HEAD) instead of the working tree")
    wv = ws.add_parser("verdict", help="record a review verdict; false alarms are suppressed until the text changes")
    wv.add_argument("repo")
    wv.add_argument("id", help="pair id from the review list")
    wv.add_argument("verdict", choices=["contradiction", "stale", "false-alarm"])
    wv.add_argument("--note")
    wt = ws.add_parser("selftest", help="plant number and rule contradictions in a scratch copy and measure recall")
    wt.add_argument("repo")
    wt.add_argument("--plants", type=int, default=5)
    wt.add_argument("--top", type=int, default=130)
    wt.add_argument("--max-cost", **cost)
    wn = ws.add_parser("lint", help="Jev checks each function against the semantic rules in docs/wiki/checks/lint.json")
    wn.add_argument("repo")
    wn.add_argument("--max-cost", **cost)
    wp = ws.add_parser("publish", help="mirror the allowlisted files and wiki pages (publish.json) into a public checkout")
    wp.add_argument("repo")
    wp.add_argument("dest", help="a checkout of the public repo; everything but its .git is replaced")
    wl = ws.add_parser("log", help="Protocol 5: session log from a Jev digest")
    wl.add_argument("repo")
    wl.add_argument("session", help="transcript path, session id (prefix), or 'latest'")
    wl.add_argument("--since")
    wl.add_argument("--slug", default="session")
    ws.add_parser("coverage", help="Protocol 6: orphan pages and broken links").add_argument("repo")


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="jevauto", description="Browser/desktop automation with a Jev fidelity layer.")
    sub = p.add_subparsers(dest="cmd", required=True)
    ks = sub.add_parser("keys", help="manage API keys in Windows Credential Manager").add_subparsers(dest="keys_cmd", required=True)
    s = ks.add_parser("set", help="store a key (hidden prompt, or --clipboard)")
    s.add_argument("name", help=f"env-var style name, e.g. {', '.join(keys.KNOWN_KEYS)}")
    s.add_argument("--clipboard", action="store_true", help="read the key from the clipboard, then clear it")
    ks.add_parser("import-env", help="copy keys already in your environment into the vault").add_argument("names", nargs="*")
    ks.add_parser("list", help="show which keys are stored (masked)")
    ks.add_parser("gui", help="open a small window to paste keys into")
    ks.add_parser("delete").add_argument("name")

    c = sub.add_parser("ctx", help="context harness: index docs, find what a task needs, digest a session")
    c.add_argument("--out", help="output folder (default: jev-automation/out)")
    cs = c.add_subparsers(dest="ctx_cmd", required=True)
    cs.add_parser("index", help="write a readable section index of a repo's Markdown docs").add_argument("repo")
    cf = cs.add_parser("find", help="Jev-picked reading list for a task, within a token budget")
    cf.add_argument("repo")
    cf.add_argument("task")
    cf.add_argument("--budget", type=int, default=25_000, help="max tokens of sections to list")
    cf.add_argument("--always", nargs="*", default=["CLAUDE.md", "docs/HANDOVER.md"],
                    help="files the session loads anyway (not scored)")
    cd = cs.add_parser("digest", help="Jev-triaged digest of a Claude Code session transcript")
    cd.add_argument("session", help="transcript path, session id (prefix), or 'latest'")
    cd.add_argument("--since", help="ISO time, e.g. 2026-09-20 — digest only what came after")
    cd.add_argument("--handover", help="current handover file; open items it resolves are set aside")

    _wiki_parser(sub)
    r = sub.add_parser("run", help="run a task")
    r.add_argument("task")
    r.add_argument("--url", help="browser: start page")
    r.add_argument("--window", help="desktop: regex for the target window title")
    r.add_argument("--launch", help="desktop: command to start the app first (use with --window)")
    r.add_argument("--headless", action="store_true")
    r.add_argument("--keep-open", action="store_true", help="leave the browser open at the end")
    r.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"], help="Claude planner effort")
    r.add_argument("--max-steps", type=int, default=40)
    r.add_argument("--jev-model", help="override the provider's default model (typesafe: jev-1.13.0)")
    return p


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")  # page text is arbitrary Unicode
    args = _parser().parse_args(argv)
    if args.cmd != "keys":
        keys.load_into_env()  # everything but key management talks to Jev or Claude
    try:
        return {"keys": _keys, "ctx": _ctx, "wiki": _wiki}.get(args.cmd, _run)(args)
    except Exception as err:
        from .consistency import CostLimit
        from .publish import PublishError

        if not isinstance(err, (CostLimit, PublishError)):
            raise
        print(err)
        return 3
