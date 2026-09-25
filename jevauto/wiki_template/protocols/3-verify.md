# Protocol 3: Verify

Check a claim against the ground truth before a wiki fix is accepted. In a code project, the
ground truth is the code, the data files and the project's own check scripts, not another doc.

## Trigger

"Run Protocol 3" or "Verify". It usually follows Protocol 1 or 2, before the fixes are committed.

## Procedure

1. **List the claims** in dispute: one line each, citing file:line on both sides.
2. **Map each claim to where the truth lives:**

   | Claim about | Source of truth | How to check |
   |---|---|---|
   | A class, function, signal or file | The code | `rg -n "<name>"`, then read the definition |
   | Behavior, invariants, counts | The project's check/test entry point | Run it (see the host `CLAUDE.md`); read the reported counts |
   | Content or tuning values | The data files | Open the resource or config that defines it |
   | History or a past decision | `git log`, the session logs, the handover | `git log -S "<phrase>"` or read the dated log |

3. **Check it.** These are local, read-only checks, so run them directly (unlike the original
   template, which printed commands for the user to run on remote systems).
4. **Decide** which side is right, and fix the other one. If the code is wrong rather than the
   docs, stop and tell the owner; a wiki pass never changes code.
