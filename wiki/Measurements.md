# Measurements: what the harness catches

Measured in September 2026 on one private project, a Godot tactics game with about 170k tokens of design
docs and 1,400 GDScript functions, using Jev through OpenJEV. One project is a small sample: treat these as
what the harness can do, not a guarantee for every codebase.

## What each part catches

| Part | Measured | Blind spots |
|---|---|---|
| `ctx find` | Reading lists of 12–25k tokens. In the first real milestone, agents with lists read ~41k tokens of docs each, against ~37.5k for agents told to read everything (they choose for themselves); the orchestrator opened ~9.5k beyond its 25k list | Without `--code` it ranks prose only, so it never sees function signatures (29 of 54 misses were code). It can also skip one sibling of a group it otherwise includes |
| `ctx digest` | A 42-turn session (~55k tokens of conversation) → ~5.6k tokens; the key decisions and preferences were all kept | Can omit a turn; cannot invent one |
| `wiki check` | Planted contradictions found: changed numbers 6/10 in the full lists and 8/10 in delta mode; flipped rule words 4/5. The first real review found 10 stale statements in 175 pairs | Contradictions inside one section, and statements without a number or rule word |
| `wiki lint` | Three rules, each scored on 20 planted violations and 40 clean functions: 20/20, 20/20 and 19/20 caught, 0/40 flagged. The first real run flagged 13 functions; after one round of rewording and one verdict, 0 | Rules that need taste rather than facts (*comments explain why*: 40%) |

Self-tests plant violations automatically, and an automatic plant can be invalid (a changed number that no
longer makes sense, a rule flip that contradicts its own sentence). Every figure above counts only plants
that were read and judged valid.

## Token savings

See [Token savings](Token-Savings): what the first milestone measured, and how to measure it on your project.

Jev's own cost is small: the full first lint of 1,410 functions was about 0.5M Jev tokens (≈$0.03 at
TypeSafe's list price), and a full contradiction run about $1.

## Replays on real work

Two questions were tested by replaying a finished milestone, with its code history and review record:

- **Does the code rule check catch logic bugs?** Six functions holding real bugs that a review later confirmed
  (a panel's forecast disagreeing with what the game executes) were judged against the project's written rule, at
  the commit before the fix. None was flagged, and neither were the fixed versions or 73 unflagged functions from
  the same files. With the rule reworded after the fact to describe this class of bug, still none was flagged, and
  two fixed functions scored higher than their buggy versions: Jev reacted to wording in the code, not to its
  logic. Such bugs often span two functions (a preview branch and a commit branch of one resolver), which a
  one-function-at-a-time check cannot see.
- **Could Jev pick the functions an agent needs, so it reads functions instead of files?** For every code file
  the milestone's agents read, Jev judged each function against that agent's task, and was scored on the
  functions the agent went on to change. At the threshold that kept most of them it found 79% (53 of 67) while
  cutting code reading by only 9%; at the threshold that cut reading by half it found 49%. Implementing agents
  fared best (8 of 8 and 15 of 16, with about a quarter less code), but an integrating agent, whose task does not
  name the code it ends up changing, got 2 of 10. Not safe as a replacement for reading.

## Known limits

- Everything depends on a Jev provider. Caches are kept per model, so a model change starts a fresh cache.
- Code extraction covers GDScript only.
- Recall figures come from one project; run `jeverifier wiki selftest` on yours before relying on them.
- Checks judge one function or one pair of statements at a time: a defect that only shows across two
  functions is invisible to them.

## Related pages

- [Overview](Overview)
- [How it works](How-It-Works)
- [Token savings](Token-Savings)
