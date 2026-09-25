"""Protocol 2's Jev-ranked contradiction list, built to be measured and to improve with use.

Pipeline (each stage fixes a failure measured on a game project with ~170k tokens of docs, 2026-09-24):
  1. claims    sentences with a number or a rule word, with file:line
  2. topics    the docs' own headings; near-duplicates merged so one subject is one topic
  3. tags      Jev Choice: each claim's top 2 topics (cached by claim text)
  4. kinds     Jev Choice: each section is current / history / plan (cached by section text),
               corrected by the owner's overrides in docs/wiki/checks/kinds.json
  5. pairs     claims that share a topic or close wording, from different sections, both current
  6. judging   Jev Noul "contradict?" on every pair; "same specific thing?" on the top 2,000
  6b. numbers  code pairs statements counting the same noun with different numbers; Jev judges only
               whether they count the same specific thing
  7. review    the top 50 number mismatches and top 130 other pairs go to Claude; each verdict is
               recorded, and a pair marked a false alarm is suppressed until either text changes

Measured on the same project (2026-09-24, OpenJEV, plants read by hand for validity):
  number contradictions: 6/10 in the full lists, 8/10 in delta mode; built by the number check's own
                         rule, so an upper bound. Before the number check: 4/10.
  rule contradictions (never -> always, ...): 4 of 5 in both; the miss was a self-contradicting plant.
Blind spots: contradictions inside one section, and statements worded without a number or rule word;
Protocol 2's sampled pairs cover those. `selftest` re-measures recall on any repo, after any change.
"""

from __future__ import annotations

from .core import Claim, CostLimit, Store, claims_of, fingerprint, merge_topics, override_kind, record_verdict  # noqa: F401
from .pipeline import DELTA_MIN_CONTRA, accept, check, quantities, report, run  # noqa: F401
from .selftest import _bump, _plant, _plant_rule, choose_plants, choose_rule_plants, selftest  # noqa: F401
