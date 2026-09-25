from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import asyncio
import random
import re
import shutil
import tempfile

from . import core as rt
from .pipeline import NUM_REVIEW
from .pipeline import REVIEW, Result, run
from .pipeline import delta
from .core import CONTRA, Claim, SAME, Store, _Jev, _judge, _stem, words


# ---------------------------------------------------------------- selftest: measure recall on this repo

_NUMWORDS = ["two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"]


# A stated quantity: a standalone number (not a section ref §11, not part of 4,979 / 1.5 / 40%, not inside a
# path or identifier) followed by the word it counts. "500 lines", "13 PAINTS", "three baselines".
_QTY = re.compile(r"(?<![\w§#/.,\-])(\d{2,4}|" + "|".join(_NUMWORDS) + r")(?![\w,.%/]|\.\d)(\s+)([A-Za-z][A-Za-z-]{2,})", re.I)


def _bump(token: str) -> str:
    if token.isdigit():
        n = int(token)
        return str(n + max(1, round(n * 0.6)))
    low = token.lower()
    k = _NUMWORDS.index(low)
    new = _NUMWORDS[(k + 3) % len(_NUMWORDS)]
    return new.capitalize() if token[0].isupper() else new


def _plant(text: str, number: str, word: str) -> str | None:
    """`text` with the quantity "<number> <word>" changed to "<bumped> <word>", or None if absent."""
    pat = re.compile(r"(?<![\w§#/.,\-])" + re.escape(number) + r"(?![\w,.%/]|\.\d)(\s+" + re.escape(word) + r")", re.I)
    new, hits = pat.subn(lambda m: _bump(number) + m.group(1), text, count=1)
    return new if hits else None


def choose_plants(claims: list[Claim], allowed: set[int] | None = None) -> list[tuple[int, tuple[str, str], int]]:
    """Candidate plants: (claim, (number, word), partner claim) where both state the same number counting
    the same thing ("500 lines" and "500 lines", "13 painting calls" and "13 PAINTS"), in different
    sections. Changing the number in one makes a contradiction by construction. `allowed` restricts both
    sides (to current-state claims); Jev's same-subject judgment in `selftest` then keeps the fair ones."""
    allowed = set(range(len(claims))) if allowed is None else allowed
    qty = {k: [(m.group(1), m.group(3)) for m in _QTY.finditer(claims[k].text)] for k in allowed}
    by_key = defaultdict(list)
    for k, qs in qty.items():
        for num, word in qs:
            by_key[(num.lower(), _stem(word))].append(k)
    out = []
    for k in sorted(allowed):
        for num, word in qty[k]:
            j = next((j for j in by_key[(num.lower(), _stem(word))] if claims[j].section.id != claims[k].section.id), None)
            if j is not None:
                out.append((k, (num, word), j))
                break
    return out


# Rule plants: a second, unrelated kind of contradiction, so the number check is not only measured with plants
# built by its own rule. Flip a modal/rule word in one of two statements that assert the same thing.
# Both sides of every flip are claim cue words, so a flipped sentence is still extracted as a claim; "only" ->
# "also" and "cannot" -> "can" were dropped after a run showed they garble sentences and drop them from
# extraction (the second is a real blind spot: a contradiction worded without a number or rule word is invisible).
RULE_FLIPS = {"must": "may", "never": "always", "always": "never"}


_RULE = re.compile(r"\b(" + "|".join(RULE_FLIPS) + r")\b", re.I)


def _flip(word: str) -> str:
    new = RULE_FLIPS[word.lower()]
    return new.upper() if word.isupper() else new.capitalize() if word[0].isupper() else new


def _plant_rule(text: str, word: str) -> str | None:
    """`text` with its first `word` flipped (must -> may, never -> always, ...), or None if absent."""
    new, hits = re.subn(rf"\b{re.escape(word)}\b", _flip(word), text, count=1)
    return new if hits else None


def choose_rule_plants(claims: list[Claim], allowed: set[int]) -> list[tuple[int, str, int]]:
    """Candidate rule plants: (claim, rule word, partner claim) where both use the same rule word and share
    at least two content words, in different sections. Jev's same-subject judgment then keeps the fair ones."""
    by_word = defaultdict(list)
    for k in sorted(allowed):
        for m in _RULE.finditer(claims[k].text):
            by_word[m.group(1).lower()].append(k)
    ws = {k: words(claims[k].text) for k in allowed}
    out = []
    for k in sorted(allowed):
        m = _RULE.search(claims[k].text)
        if not m:
            continue
        j = next((j for j in by_word[m.group(1).lower()]
                  if claims[j].section.id != claims[k].section.id and len(ws[k] & ws[j]) >= 2), None)
        if j is not None:
            out.append((k, m.group(1), j))
    return out


async def _fair(repo: Path, res: Result, cands: list, n: int, seed: int, max_cost: float | None):
    """Keep candidates Jev judges to be about the same specific thing (≥0.7) that do not already contradict
    (<0.5), at most n//2 per file. Returns (picked, number of candidates judged, number fair)."""
    rng = random.Random(seed)
    rng.shuffle(cands)
    cands = cands[:max(400, 40 * n)]  # rule candidates are mostly unrelated statements sharing "must"; judge enough to find n fair ones
    store = Store(repo)
    judged = store.load("judged")
    try:
        async with rt._client() as client:
            jv = _Jev(client, max_cost)
            pairs = [(k, j) for k, _, j in cands]
            same = await _judge(jv, res.claims, pairs, SAME, "Are `first` and `second` about the same specific thing?", judged, "s")
            contra = await _judge(jv, res.claims, pairs, CONTRA, "Do `first` and `second` contradict each other?", judged, "c")
    finally:
        store.save("judged", judged)
    fair = [(k, spec, j, s) for (k, spec, j), s, c in zip(cands, same, contra) if s >= 0.7 and c < 0.5]
    picked, per_file = [], defaultdict(int)
    for k, spec, j, s in fair:
        if per_file[res.claims[k].section.file] < max(1, n // 2) and all(k not in (p[0], p[2]) for p in picked):
            picked.append((k, spec, j, s))
            per_file[res.claims[k].section.file] += 1
        if len(picked) == n:
            break
    return picked, len(cands), len(fair)


def _mutate(kind: str, spec, text: str) -> str | None:
    return _plant(text, *spec) if kind == "number" else _plant_rule(text, spec)


def _describe(kind: str, spec) -> str:
    if kind == "number":
        num, word = spec
        return f"{num} {word} → {_bump(num)} {word}"
    return f"{spec} → {_flip(spec)}"


def _plan(repo: Path, base: Result, kinds: tuple[str, ...], n: int, seed: int, max_cost: float | None):
    """Fair plants of each kind, no claim used twice. Returns (plan, per-kind candidate counts)."""
    current = {i for i, c in enumerate(base.claims) if base.kinds[c.section.id] == "current"}
    plan, counts = [], {}
    for kind in kinds:
        cands = choose_plants(base.claims, current) if kind == "number" else choose_rule_plants(base.claims, current)
        taken = {x for p in plan for x in (p[1], p[3])}
        cands = [c for c in cands if c[0] not in taken and c[2] not in taken]
        left = None if max_cost is None else max(0.0, max_cost - base.stats["cost_usd"])
        picked, n_cands, n_fair = asyncio.run(_fair(repo, base, cands, n, seed, left))
        counts[kind] = {"candidates": n_cands, "fair": n_fair}
        plan += [(kind, k, spec, j, same) for k, spec, j, same in picked]
    return plan, counts


def _plant_in_file(root: Path, claim: Claim, kind: str, spec) -> bool:
    """Change the claim in its file under `root`, anchored at the claim's own first words so an earlier
    sentence in the same paragraph is never the one changed."""
    path = root / claim.section.file
    text = path.read_text(encoding="utf-8")
    start = sum(len(l) + 1 for l in text.split("\n")[:claim.line - 1])  # the claim's paragraph starts here
    window = text[start:start + 4000]
    head = re.compile(r"\W+".join(re.escape(w) for w in re.findall(r"\w+", claim.text)[:6]))
    at = head.search(window)
    planted = _mutate(kind, spec, window[at.start():]) if at else None
    if planted is None:
        return False
    path.write_text(text[:start + at.start()] + planted + text[start + 4000:], encoding="utf-8", newline="\n")
    return True


def _apply(repo: Path, secs, base: Result, plan, max_cost: float | None):
    """Copy the docs to a scratch folder, plant there, and run the pipeline on the copy."""
    from ..wiki import _wiki_and_docs

    with tempfile.TemporaryDirectory(prefix="jeverifier-selftest-") as tmp:
        root = Path(tmp)
        for f in {s.file for s in secs}:
            (root / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(repo / f, root / f)
        changed = [(kind, base.claims[k], spec, base.claims[j], same) for kind, k, spec, j, same in plan
                   if _plant_in_file(root, base.claims[k], kind, spec)]
        left = None if max_cost is None else max(0.0, max_cost - base.stats["cost_usd"])
        return changed, run(root, _wiki_and_docs(root), cache_name=repo.resolve().name, max_cost=left)


def _score_plant(res: Result, maps: dict, top: int, kind: str, a: Claim, spec, b: Claim, same: float) -> dict:
    """Where one planted contradiction landed in each list, and why it was missed if it was."""
    planted_text = _mutate(kind, spec, a.text)
    mut = next((k for k, c in enumerate(res.claims) if c.section.file == a.section.file and c.text == planted_text), None)
    partner = next((k for k, c in enumerate(res.claims) if c.text == b.text and c.section.file == b.section.file), None)
    row = {"type": kind, "where": f"{a.section.file}:{a.line}", "change": _describe(kind, spec),
           "partner": f"{b.section.file}:{b.line}", "same_before": round(same, 2), "rank": None, "number_rank": None,
           "found": False, "found_delta": False, "why": "planted claim not re-extracted",
           "planted_text": planted_text or a.text, "partner_text": b.text}
    if mut is None or partner is None:
        return row
    pq = (min(mut, partner), max(mut, partner))
    row["kind"] = res.kinds[res.claims[mut].section.id]
    if pq in maps["num_rank"]:
        row["number_rank"] = maps["num_rank"][pq] + 1
        row["number_same"] = round(res.numeric[maps["num_rank"][pq]][0], 2)
    if pq in res.scores:
        c, s = res.scores[pq]
        row["contra"] = round(c, 2)
        if s is not None:
            row.update(same=round(s, 2), rank=maps["rank"][pq] + 1)
    in_general = row["rank"] is not None and row["rank"] <= top
    in_numbers = row["number_rank"] is not None and row["number_rank"] <= NUM_REVIEW
    row["found"] = in_general or in_numbers
    row["found_delta"] = pq in maps["delta"]
    if row["found"]:
        row["why"] = "found in " + " and ".join(x for x, ok in (("numbers", in_numbers), ("general", in_general)) if ok)
    elif row["kind"] != "current":
        row["why"] = f"section relabelled {row['kind']} after the edit"
    elif pq not in res.scores and pq not in maps["num_rank"]:
        row["why"] = "not paired"
    else:
        row["why"] = "ranked too low"
    return row


def _score(res: Result, base: Result, changed, top: int):
    """Score every plant against the full lists and against delta mode. The unplanted docs are the accepted
    baseline, so the planted statements are the only changed text -- what a later `check` shows after an edit."""
    d_general, d_numeric, _ = delta(res, {c.key for c in base.claims}, top, NUM_REVIEW)
    maps = {"rank": {(i, j): r for r, (_, _, _, i, j) in enumerate(res.ranked)},
            "num_rank": {(i, j): r for r, (_, i, j, _, _) in enumerate(res.numeric)},
            "delta": {(i, j) for *_, i, j in d_general} | {(i, j) for _, i, j, _, _ in d_numeric}}
    return [_score_plant(res, maps, top, *c) for c in changed], len(d_general) + len(d_numeric)


def selftest(repo: Path, n: int = 5, top: int = REVIEW, seed: int = 7, max_cost: float | None = 1.0,
             kinds: tuple[str, ...] = ("number", "rule")) -> dict:
    """Plant n contradictions of each kind in a scratch copy of the docs and report, per plant, both texts,
    whether it was paired, how Jev scored it and where it ranked in each list. Nothing in the repo is touched.
    Uses the repo's caches, so only the planted claims and their pairs cost anything beyond a normal check.

    number: change a stated count in one of two statements counting the same thing. This is how the number
            check itself finds pairs, so its recall on these plants is an upper bound.
    rule:   flip a rule word (must -> may, never -> always, ...) in one of two statements of the same rule.
    """
    from ..wiki import _wiki_and_docs

    secs = _wiki_and_docs(repo)
    base = run(repo, secs, max_cost=max_cost)
    plan, counts = _plan(repo, base, kinds, n, seed, max_cost)
    changed, res = _apply(repo, secs, base, plan, max_cost)
    rows, delta_listed = _score(res, base, changed, top)
    by_type = {t: {"planted": sum(r["type"] == t for r in rows), "found": sum(r["type"] == t and r["found"] for r in rows),
                   "found_delta": sum(r["type"] == t and r["found_delta"] for r in rows), **counts.get(t, {})}
               for t in kinds}
    return {"plants": rows, "by_type": by_type, "top": top, "top_numbers": NUM_REVIEW, "delta_listed": delta_listed,
            "cost_usd": round(base.stats["cost_usd"] + res.stats["cost_usd"], 3), "stats": res.stats}
