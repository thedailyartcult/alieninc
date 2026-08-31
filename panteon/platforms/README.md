# Panteon Platforms — Modular Decomposition

Shell:  (core pages + router + auth + loader). This dir holds the 9 lazy platforms.

## Structure
-  — single source of truth (sidebar + lazy loader). Shell fetches it on first .
-  — sidebar metadata for one platform (title/badge/pages). LLM reads only this + registry, not whole shell.
-  — version, apiDependencies, budgets.
-  — one file per  (extracted from admin.html). Lazy-fetched on first navigation; inline fallback still exists in shell for now so no breakage.
-  — platform JS (future). Today empty placeholder; shell still inlines handlers. Next step is to move  functions per platform into module.js and have loader inject it.
-  — cross-platform contracts (api.js, design-tokens.md).

## LLM Focus Protocol (operational rigor)
To work on ONE platform (e.g. YONO):
1. Read  (1k tokens)
2. Read  +  (1k tokens)
3. Read  needed (max 8k tokens per page)
4. Read  (max 16k)
Total < 25k — fits 32k windows. Do NOT read other .

## Cohesive Panel Guarantee
-  still renders all nav visibly (via registry-driven fallback) and all pages work — loader falls back to inline HTML if fetch fails.
-  is now  with  +  preflight, so existing  switch keeps same behavior.
- Platform Select () still filters  visibility; registry  mirrors it.

## Budgets (CI enforced)
- Shell  max 6000 lines (today 26088 — will shrink as pages move out)
- Per platform  max 900 lines / 16000 tokens
- Per page max 8000 tokens

## Next extraction steps
1. Move YONO  into 
2. Move Spinal Cracker fusion map ( 2289 lines) into 
3. Delete inline  for moved platforms once lazy path proven (keep 1 release with dual fallback)
