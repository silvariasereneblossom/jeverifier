# JeVerifier — overview

JeVerifier keeps a codebase maintainable and its docs consistent while Claude works on it. It puts
[TypeSafe's Jev](https://docs.typesafe.ai), a fast classifier, beside a Claude coding session to run checks that
would be too costly to have a frontier model run on every change: every function against the project's
architectural rules, and every statement in the docs against the others. It also picks the docs and code a task
needs and digests sessions for handover. Claude reviews what Jev surfaces, once, and later runs show only what
changed. Token savings are a modest, secondary benefit ([Token savings](Token-Savings)).

Jev only selects, ranks and labels. It never writes summaries or code, so it cannot invent content; its
failure mode is leaving something out, which every part below measures.

## The parts

| Part | Command | Source |
|---|---|---|
| Code rule check | `jeverifier wiki lint` | [lint.py](https://github.com/silvariasereneblossom/jeverifier/blob/main/jeverifier/lint.py) |
| Doc contradiction check | `jeverifier wiki check / accept / verdict / selftest` | [consistency/](https://github.com/silvariasereneblossom/jeverifier/blob/main/jeverifier/consistency/__init__.py) |
| Living wiki in each repo | `jeverifier wiki init / map / coverage` | [wiki.py](https://github.com/silvariasereneblossom/jeverifier/blob/main/jeverifier/wiki.py) |
| Reading list for a task | `jeverifier ctx find` (MCP `context_find`) | [ctx.py](https://github.com/silvariasereneblossom/jeverifier/blob/main/jeverifier/ctx.py) |
| Session digest for handover | `jeverifier ctx digest`, `jeverifier wiki log` | [ctx.py](https://github.com/silvariasereneblossom/jeverifier/blob/main/jeverifier/ctx.py), [wiki.py](https://github.com/silvariasereneblossom/jeverifier/blob/main/jeverifier/wiki.py) |
| API keys without env vars | `jeverifier keys gui` | [keys.py](https://github.com/silvariasereneblossom/jeverifier/blob/main/jeverifier/keys.py) |

How the parts work: [How it works](How-It-Works). What they catch:
[Measurements](Measurements). What they save: [Token savings](Token-Savings).

## Related pages

- [Home](Home)
- [How it works](How-It-Works)
- [Measurements](Measurements)
- [Token savings](Token-Savings)
