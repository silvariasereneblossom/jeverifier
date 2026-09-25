# Measurements: what the harness catches

Measured in September 2026 on one private project, a Godot tactics game with about 170k tokens of design
docs and 1,400 GDScript functions, using Jev through OpenJEV. One project is a small sample: treat these as
what the harness can do, not a guarantee for every codebase.

## What each part catches

| Part | Measured | Blind spots |
|---|---|---|
| `ctx find` | Reading lists of 12–25k tokens against ~168k for all docs | Missed 2 relevant sections on one test task; the list is a starting point |
| `ctx digest` | A 42-turn session (~55k tokens of conversation) → ~5.6k tokens; the key decisions and preferences were all kept | Can omit a turn; cannot invent one |
| `wiki check` | Planted contradictions found: changed numbers 6/10 in the full lists and 8/10 in delta mode; flipped rule words 4/5. The first real review found 10 stale statements in 175 pairs | Contradictions inside one section, and statements without a number or rule word |
| `wiki lint` | Three rules, each scored on 20 planted violations and 40 clean functions: 20/20, 20/20 and 19/20 caught, 0/40 flagged. The first real run flagged 13 functions; after one round of rewording and one verdict, 0 | Rules that need taste rather than facts (*comments explain why*: 40%) |

Self-tests plant violations automatically, and an automatic plant can be invalid (a changed number that no
longer makes sense, a rule flip that contradicts its own sentence). Every figure above counts only plants
that were read and judged valid.

## Token savings

See [Projected token savings](Token-Savings): the measured savings, a formula for your own repo, and worked examples.

Jev's own cost is small: the full first lint of 1,410 functions was about 0.5M Jev tokens (≈$0.03 at
TypeSafe's list price), and a full contradiction run about $1.

## Known limits

- Everything depends on a Jev provider. Caches are kept per model, so a model change starts a fresh cache.
- Code extraction covers GDScript only.
- Recall figures come from one project; run `jevauto wiki selftest` on yours before relying on them.

## Related pages

- [Overview](Overview)
- [How it works](How-It-Works)
- [Projected token savings](Token-Savings)
