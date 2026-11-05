# AI Search Readiness (GEO/AEO) Findings — alieninc.tech

Checker: `agentic_check.py` v2.4.0. This is the category where the site scores
lowest and has the highest leverage — especially given Alien Inc's positioning.

## Score summary

```
{"P0": {"warn": 1, "pass": 2},
 "P1": {"info": 3, "pass": 2},
 "P2": {"info": 1, "na": 4},
 "P3": {"info": 1, "na": 3}}
```

## What works

- **P0 pass — primary content present without JavaScript.** Crawlers and AI
  agents can read the site without executing JS. This is the single most
  important GEO gate and it is already satisfied.
- **P0 pass — robots.txt reachable.**
- **P1 pass — user-triggered agents respected.** No rogue auto-submitting forms.
- **P1 pass — unknown URLs return a real 404** (not a soft 404 that confuses
  index models).
- **P1 info — Content-Signal preference declared** (a `Content-Signal` header
  exists, letting publishers express AI-training preference).
- **P2 info — WebMCP tools for forms and transactions** are annotated.
- **P3 info — forms annotated for declarative WebMCP** (static scan).

## Findings

### High — `llms.txt` returns 404
The root `/llms.txt` and `/llms-full.txt` both return HTTP 404. The
`agentic_check` output is explicit:

> "No /llms.txt. Lighthouse drops the audit from the fraction; publishing a
> valid one adds a counted pass. Include an H1, a '>' summary and Markdown links."

Note: an earlier pass of `agentic_check` reported `llms.txt follows the
Lighthouse rules` while a direct fetch returned 404 — the info-level line
reflects the *format rules*, not an existing file. **There is no llms.txt.**

**Fix:** publish `/llms.txt` at the domain root:

```markdown
# Alien Inc

> Seven-company operating group and independent guardian of Philippine
> digital infrastructure. Sabotage detection, facility verification,
> recoverable archives. Founded 2016 by Patrick Neil Alcantara.

## Companies
- [Centra](https://centra.alieninc.tech/): Trust and security portal
- [Panteon](https://panteon.alieninc.tech/): Secure portal and platform
- [Genesis](https://genesis.alieninc.tech/): Research and exploration
- [Immanuel](https://immanuel.alieninc.tech/): Global security & risk management
- [A-SAN](https://a-san.alieninc.tech/): ASEAN aerospace navigator
- [KMT](https://kmt.alieninc.tech/): Strategic clarity, applied AI
- [Rousseau](https://rousseau.alieninc.tech/): ...
- [The Daily Art Cult](https://thedailyartcult.lol): audiobooks, philosophy

## Key pages
- [About](https://alieninc.tech/about.html)
- [Founder](https://alieninc.tech/founder.html)
- [Mission](https://alieninc.tech/mission.html)
- [Compliance report](https://alieninc.tech/compliance.html)
```

### High — robots.txt blocks 10+ AI crawlers, contradicting GEO goals
The site declares `llms.txt`-style readiness and a `Content-Signal` preference,
yet `robots.txt` opens with:

```
# AI Crawlers — EXPRESSLY PROHIBITED
User-agent: GPTBot        Disallow: /
User-agent: CCBot         Disallow: /
User-agent: Google-Extended Disallow: /
User-agent: anthropic-ai  Disallow: /
User-agent: Claude-Web    Disallow: /
User-agent: cohere-ai     Disallow: /
User-agent: PerplexityBot Disallow: /
User-agent: Bytespider    Disallow: /
User-agent: Diffbot       Disallow: /
```

The `agentic_check` P0 warning is the right framing:

> "Blocking an AI search crawler removes the site from that engine's answers.
> Confirm this is intended."

**This is a policy decision, not a bug.** The tools cannot resolve it for you.
The trade-off:

| Agent | Blocked? | What you lose by blocking |
|---|---|---|
| GPTBot | yes | OpenAI training corpus — lowest GEO value, highest privacy value |
| CCBot | yes | Common Crawl — feeds many open models |
| Google-Extended | yes | **Gemini training + AI Overviews grounding.** Blocking this directly suppresses AI Overview visibility |
| PerplexityBot | yes | Perplexity answer citations |
| Claude-Web / anthropic-ai | yes | Anthropic product answers |
| Bytespider | yes | ByteDance/TikTok models |
| Diffbot | yes | entity/knowledge-graph extraction |

**Recommendation:** if GEO/AI Overviews is a real goal, unblock
`Google-Extended` and `PerplexityBot` at minimum. Keep `GPTBot`, `CCBot`,
`Bytespider` blocked if you want to avoid training corpora. Note that
`Googlebot` (search indexing) is *not* blocked — so classic SEO is unaffected
either way; only the AI-answer surfaces are.

### Info — ai-catalog.json and A2A agent card absent
`ai-catalog.json` (Agentic Resource Discovery), the A2A agent card
(`/.well-known/agent-card.json`), UCP commerce profile, and OAuth
Protected Resource / Authorization Server metadata all report `na`.

**Fix, if agent discoverability is a product goal:** publish
`/ai-catalog.json` and an A2A agent card. For a corporate umbrella site this
is optional; for Panteon-as-a-product it becomes relevant.
