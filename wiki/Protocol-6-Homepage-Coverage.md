# Protocol 6: Homepage Coverage

Every wiki page must be reachable from `home.md` by following links, and every relative link
must point at a file that exists.

## Trigger

"Run Protocol 6" or "check coverage".

## Procedure

1. Run `jeverifier wiki coverage <repo>`. It crawls relative links from `home.md` (wiki pages and the
   project docs they link into) and prints unreachable wiki pages and broken links.
2. Link every orphan from the most specific page it belongs under, not straight from `home.md`
   unless it is a top-level topic.
3. Fix or remove every broken link, then re-run until the report is clean.
