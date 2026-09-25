# jevauto — overview

jevauto puts [TypeSafe's Jev](https://docs.typesafe.ai), a fast classifier, around two kinds of work where a
large model is expensive or unreliable on its own:

1. **Automation.** Claude plans browser and Windows-app actions; Jev checks every action before it runs
   (right element? risky? blocked by a CAPTCHA or sign-in?), and plain code decides what happens. See the
   [README](https://github.com/silvariasereneblossom/jevauto/blob/main/README.md).
2. **Coding work.** Jev does the repetitive reading a coding session would otherwise pay a large model for:
   picking the docs a task needs, digesting a session for handover, and checking docs and code against the
   project's own rules. Claude reviews what Jev surfaces, once, and later runs show only what changed.

Jev only selects, ranks and labels. It never writes summaries or code, so it cannot invent content; its
failure mode is leaving something out, which every part below measures.

## The parts

| Part | Command | Source |
|---|---|---|
| Action gate for automation | `jevauto run`, MCP tools `open_browser`, `act`, … | [gate.py](https://github.com/silvariasereneblossom/jevauto/blob/main/jevauto/gate.py), [policy.py](https://github.com/silvariasereneblossom/jevauto/blob/main/jevauto/policy.py) |
| Reading list for a task | `jevauto ctx find` (MCP `context_find`) | [ctx.py](https://github.com/silvariasereneblossom/jevauto/blob/main/jevauto/ctx.py) |
| Session digest for handover | `jevauto ctx digest`, `jevauto wiki log` | [ctx.py](https://github.com/silvariasereneblossom/jevauto/blob/main/jevauto/ctx.py), [wiki.py](https://github.com/silvariasereneblossom/jevauto/blob/main/jevauto/wiki.py) |
| Living wiki in each repo | `jevauto wiki init / map / coverage` | [wiki.py](https://github.com/silvariasereneblossom/jevauto/blob/main/jevauto/wiki.py) |
| Doc contradiction check | `jevauto wiki check / accept / verdict / selftest` | [consistency/](https://github.com/silvariasereneblossom/jevauto/blob/main/jevauto/consistency/__init__.py) |
| Code rule check | `jevauto wiki lint` | [lint.py](https://github.com/silvariasereneblossom/jevauto/blob/main/jevauto/lint.py) |
| API keys without env vars | `jevauto keys gui` | [keys.py](https://github.com/silvariasereneblossom/jevauto/blob/main/jevauto/keys.py) |

How the coding parts work: [How it works](How-It-Works). What they catch:
[Measurements](Measurements). What they save: [Projected token savings](Token-Savings).

## Related pages

- [Home](Home)
- [How it works](How-It-Works)
- [Measurements](Measurements)
- [Projected token savings](Token-Savings)
