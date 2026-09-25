# Token savings: what has been measured

**Short version.** In the first milestone measured, reading lists did not reduce what agents read. Agents told
to read everything already pick out about a fifth of the docs themselves, and all doc reading together is only
6–12% of the token bill. So far, JeVerifier's measured value is in the checks, not in reading less. Code reading
is the larger share, and per-phase lists that include code APIs (`ctx find --code`) are the version being
measured next.

## The first milestone, measured

A four-phase implementation milestone in a game project with about 170k tokens of design docs, one agent per
phase, each given a ~25k reading list. It is compared with an earlier milestone of the same shape whose agents
were told to read the full docs. Every tool result in each agent's transcript was classified as doc or code;
"carried" weights each read by the turns remaining after it, since a token read early is re-sent every turn.

| | With reading lists | Told to read everything |
|---|---|---|
| Doc tokens read | 164k (41k per agent) | 150k (37.5k per agent) |
| Code tokens read | 314k | 451k |
| Doc tokens carried | 19.7M (11.6% of cache reads) | 24.9M (6.3%) |
| Code tokens carried | 33.8M | 103.8M |

What it shows:

- **A full read order is a ceiling nobody reads.** Agents told to read everything read about 37.5k tokens of
  docs each. Agents with a 25k list read slightly more, once their misses and the ranges they had to find again
  (lists made before earlier phases moved the docs) are counted.
- **The earlier milestone cost more because of its task.** One refactoring agent that read 254k tokens of code
  carried 69% of that milestone's cache reads. The two milestones' totals are not a measure of the lists.
- **The ceiling for reading lists is small.** Doc reading carried 6–12% of cache reads, so perfect lists could
  save at most that, and realistic ones perhaps a third of it.
- **Code is the bigger pool.** Code carry was 1.7–4× doc carry, and 29 of the 54 reading-list misses were code,
  which is what `ctx find --code` addresses.

## What does pay off today

- **Checks that would not otherwise run.** On that project, the first doc review found 10 stale statements, and
  a milestone contract's review found 4 real errors before implementation (3 in the contract, 1 stale line in
  the architecture doc). After the first review, a doc re-check lists only a few pairs per edited statement, and
  a code re-check costs nothing for unchanged functions.
- **Handover digests.** A 42-turn session's conversation (~55k tokens) digests to ~5.6k of verbatim decisions,
  preferences and open items. What that saves depends on what the next session would otherwise read.

## Measuring it on your project

Classify each agent's reads as doc or code and weight each by the turns remaining after it. The doc share of
that carry is the most any reading list can save; compare it with the same measurement for the code share
before deciding where to spend effort.

## Next

Lists generated per phase against the tree that phase inherits, with the contract in `--always` and code APIs
ranked alongside docs (`--code`), measured the same way: how many code misses the lists cover, and whether
code carry falls.

## Related pages

- [Measurements](Measurements)
- [How it works](How-It-Works)
- [Overview](Overview)
