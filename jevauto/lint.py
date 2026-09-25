"""`jevauto wiki lint`: Jev checks each function against the project's semantic rules (docs/wiki/checks/lint.json).

Only for rules no parser can check ("UI code never writes application state"); mechanical rules belong in the project's
own tools. A rule's `exceptions` list holds its sanctioned exceptions, each documented in the project first. Answers are cached by rule text + function text, so a repeat run pays only for changed functions, and a
finding marked false-alarm (`jevauto wiki verdict`) stays silent until that function changes. GDScript only; add
a language when a project needs one.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import re
from pathlib import Path

from typesafe_sdk import Noul

from .consistency import core

RULES = "docs/wiki/checks/lint.json"
GD_FUNC = re.compile(r"(?:static )?func (\w+)")


def functions(repo: Path, prefixes: list[str]) -> list[dict]:
    """Every top-level GDScript function under the prefixes, with its ## doc comment."""
    units = []
    for f in sorted({f for p in prefixes for f in (repo / p).rglob("*.gd")}):
        lines = f.read_text(encoding="utf-8").split("\n")
        starts = [i for i, line in enumerate(lines) if GD_FUNC.match(line)]
        docs = []
        for s in starts:
            d = s
            while d > 0 and lines[d - 1].startswith("##"):
                d -= 1
            docs.append(d)
        for n, s in enumerate(starts):
            end = docs[n + 1] if n + 1 < len(starts) else len(lines)
            units.append({"where": f"{f.relative_to(repo).as_posix()}:{s + 1}", "name": GD_FUNC.match(lines[s]).group(1),
                          "code": "\n".join(lines[docs[n]:end]).rstrip()})
    return units


def _applies(rule: dict, u: dict) -> bool:
    return u["where"].startswith(tuple(rule["paths"])) and any(s in u["code"] for s in rule.get("contains", [""]))


def text(rule: dict) -> str:
    """The rule as Jev reads it: the principle, then its sanctioned exceptions (mirroring the project docs' list)."""
    return rule["rule"] + "".join(f" Allowed exception: {e}" for e in rule.get("exceptions", []))


def _key(rule: dict, u: dict) -> str:
    return f"{core._hash(text(rule) + rule['true'] + rule['false'])}:{core._hash(u['code'])}"


async def _ask(jv: core._Jev, units: list[dict], rules: list[dict], cache: dict) -> int:
    """One request per function, one Noul per applicable rule; the code is the state, the rule the question."""
    todo = [(u, [r for r in rules if _applies(r, u) and _key(r, u) not in cache]) for u in units]
    todo = [(u, rs) for u, rs in todo if rs]
    jv.afford(f"linting {len(todo):,} functions", sum(len(u["code"]) // 4 + 150 * len(rs) for u, rs in todo))

    async def one(u, rs):
        r = await jv.call({"file": u["where"].rsplit(":", 1)[0], "code": u["code"]},
                          {f"r{i}": Noul(instructions={"rule": text(rule), "question": "Does the function in `code` break `rule`?"},
                                         criteria={"true": rule["true"], "false": rule["false"]}) for i, rule in enumerate(rs)})
        for i, rule in enumerate(rs):
            cache[_key(rule, u)] = r.nouls[f"r{i}"].noul
    await asyncio.gather(*(one(u, rs) for u, rs in todo))
    return len(todo)


def lint(repo: Path, max_cost: float | None = 1.0) -> tuple[Path, dict]:
    rules = json.loads((repo / RULES).read_text(encoding="utf-8"))
    units = functions(repo, sorted({p for r in rules for p in r["paths"]}))
    store = core.Store(repo)
    cache, verdicts = store.load("lint"), store.verdicts()

    async def go():
        async with core._client() as client:
            jv = core._Jev(client, max_cost)
            try:
                return await _ask(jv, units, rules, cache), jv.spent
            finally:
                store.save("lint", cache)  # keep what was paid for even if a request fails
    asked, spent = asyncio.run(go())
    findings = []
    for rule in rules:
        for u in units:
            fid = f"lint:{rule['id']}:{core._hash(u['code'])[:10]}"
            p = cache.get(_key(rule, u), 0.0) if _applies(rule, u) else 0.0
            if p >= rule.get("threshold", 0.5) and verdicts.get(fid, {}).get("verdict") != "false-alarm":
                findings.append({"id": fid, "rule": rule["id"], "p": round(p, 2), **u})
    stats = {"functions": len(units), "asked_jev": asked, "findings": len(findings),
             "cost_usd": round(spent * core.PRICE_PER_TOKEN, 4)}
    return _report(repo, findings, stats), stats


def _report(repo: Path, findings: list[dict], stats: dict) -> Path:
    lines = [f"# Lint — {repo.resolve().name} — {dt.date.today().isoformat()}", "",
             f"{stats['findings']} findings in {stats['functions']:,} functions ({stats['asked_jev']} sent to Jev this run). "
             "Open each at file:line; fix it, or record `jevauto wiki verdict <repo> <id> false-alarm`.", ""]
    for rule in sorted({f["rule"] for f in findings}):
        lines += [f"## {rule}", ""] + [f"- `{f['id']}` · {f['where']} `{f['name']}` · p={f['p']}"
                                       for f in sorted(findings, key=lambda f: -f["p"]) if f["rule"] == rule] + [""]
    dest = core.OUT / repo.resolve().name / f"lint-{dt.date.today().isoformat()}.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return dest
