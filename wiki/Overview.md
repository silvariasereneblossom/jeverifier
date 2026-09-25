# JeVerifier — overview

JeVerifier puts [TypeSafe's Jev](https://docs.typesafe.ai), a fast classifier, under a Claude coding session. Jev
does the repetitive reading the session would otherwise pay a large model for: picking the docs a task needs,
digesting a session for handover, and checking docs and code against the project's own rules. Claude reviews what
Jev surfaces, once, and later runs show only what changed.

Jev only selects, ranks and labels. It never writes summaries or code, so it cannot invent content; its
failure mode is leaving something out, which every part below measures.

## The parts

| Part | Command | Source |
|---|---|---|
| Reading list for a task | `jeverifier ctx find` (MCP `context_find`) | [ctx.py](https://github.com/silvariasereneblossom/jeverifier/blob/main/jeverifier/ctx.py) |
| Session digest for handover | `jeverifier ctx digest`, `jeverifier wiki log` | [ctx.py](https://github.com/silvariasereneblossom/jeverifier/blob/main/jeverifier/ctx.py), [wiki.py](https://github.com/silvariasereneblossom/jeverifier/blob/main/jeverifier/wiki.py) |
| Living wiki in each repo | `jeverifier wiki init / map / coverage` | [wiki.py](https://github.com/silvariasereneblossom/jeverifier/blob/main/jeverifier/wiki.py) |
| Doc contradiction check | `jeverifier wiki check / accept / verdict / selftest` | [consistency/](https://github.com/silvariasereneblossom/jeverifier/blob/main/jeverifier/consistency/__init__.py) |
| Code rule check | `jeverifier wiki lint` | [lint.py](https://github.com/silvariasereneblossom/jeverifier/blob/main/jeverifier/lint.py) |
| API keys without env vars | `jeverifier keys gui` | [keys.py](https://github.com/silvariasereneblossom/jeverifier/blob/main/jeverifier/keys.py) |

How the parts work: [How it works](How-It-Works). What they catch:
[Measurements](Measurements). What they save: [Projected token savings](Token-Savings).

## Related pages

- [Home](Home)
- [How it works](How-It-Works)
- [Measurements](Measurements)
- [Projected token savings](Token-Savings)
