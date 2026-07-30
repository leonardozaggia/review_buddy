# How Zotero actually downloads PDFs (and what Review Buddy copies)

If you paste a list of DOIs into Zotero's **Add Item(s) by Identifier** button,
you get far more PDFs than a naive script does. It is natural to assume the
[Zotero translators](https://github.com/zotero/translators) are doing the
downloading. **They are not.** This document explains the real mechanism, since
understanding it is what makes the difference reproducible.

## The common misconception

> "The translators fetch the PDF from a DOI."

They don't. A translator is a **page parser**. It takes a document you have
*already fetched* and extracts structured data from it. It cannot get you past a
paywall, a login, or a bot check, and for an identifier there is no page to parse
in the first place.

You can verify this directly against a translation server:

```bash
curl -X POST http://127.0.0.1:1969/search \
     -H "Content-Type: text/plain" -d "10.1016/j.neuron.2018.01.048"
```

The response is metadata with **`"attachments": null`** — title, DOI, URL, no PDF.

## What Zotero actually does

"Add by identifier" is two separate phases.

### Phase 1 — identifier → metadata

A *search translator* (DOI Content Negotiation / Crossref, PubMed, arXiv,
ISBN…) turns the identifier into a bibliographic item. This is the
`/search` endpoint above. Still no PDF.

### Phase 2 — metadata → file

This is the part that matters, and it lives in
`chrome/content/zotero/xpcom/attachments.js`, not in the translators repo.
`Zotero.Attachments.getFileResolvers()` builds an **ordered list of resolvers**:

| # | Resolver | Produces |
|---|----------|----------|
| 1 | `doi` | `pageURL = https://doi.org/<DOI>` |
| 2 | `url` | `pageURL = <item's url field>` |
| 3 | `oa` (PMCID) | `pageURL = https://pmc.ncbi.nlm.nih.gov/articles/<PMCID>/` |
| 4 | `oa` (DOI) | `POST https://services.zotero.org/oa/search {doi}` → `[{url?, pageURL?, version}]` |
| 5 | `custom` | user-configured resolvers (e.g. a library proxy) |

Then `addFileFromURLs()` walks that list. For each entry:

- if it has a direct **`url`** → download it, verify the content type is a PDF;
- if it has a **`pageURL`** → fetch the page (following redirects manually, with
  per-domain delays and backoff), then:
  - if the response is *already* a PDF → save it;
  - otherwise parse the HTML and call
    `Zotero.Utilities.Internal.getFileFromDocument(doc)` — **this is where the
    translators finally come in.** It runs the web translators on that document
    and returns the first attachment whose mimeType is `application/pdf`.

So the translators *are* used for PDFs — but only as the **last step**, applied
to a landing page you already downloaded. They are the extractor, not the fetcher.

### The piece nobody talks about: Zotero's own OA index

Resolver #4 posts the DOI to **`https://services.zotero.org/oa/search`**, a
curated Unpaywall-derived index Zotero runs. It is not part of the translators,
and it is a large part of why the app finds so much. Examples measured live:

| DOI | Plain Unpaywall | Zotero OA index |
|---|---|---|
| `10.1016/j.neuron.2018.01.048` | nothing | `cell.com/article/S0896627318300734/pdf` (direct PDF) |
| `10.1038/nature14539` | nothing | HAL preprint copy |
| `10.1111/j.1460-9568.2011.07677.x` | nothing | PMC copy |

## What Review Buddy now does

`src/searchers/zotero_client.py` reproduces the same chain:

```python
client.iter_pdf_candidates(doi=..., url=..., pmcid=...)
# yields (pdf_url, referer, method) in Zotero's resolver order:
#   zotero:doi:meta, zotero:url:translator, zotero:pmc, zotero:oa, ...
```

For each `pageURL` it first reads the `citation_pdf_url` meta tag (cheap — and
what Zotero's Embedded Metadata translator reads anyway), then falls back to the
translation server so a site-specific translator can find the link.

The OA index works **without** the local translation server, so it helps even if
you never start it.

## Why a script still loses to the desktop app

Once you copy the resolver chain, the remaining gap is not about translators at
all — it is about **looking like a browser**:

1. **Bot protection.** Elsevier/ScienceDirect and Wiley sit behind Cloudflare,
   which fingerprints the TLS/HTTP2 handshake. A Python `requests` client gets
   `HTTP 403` no matter what `User-Agent` you set. Zotero is a real Gecko
   browser, so it passes. On a 123-paper corpus, **37 of our failures were 403s
   — including MDPI, PLOS and PMC, which are fully open access.** Those are not
   paywalls; they are "you don't look like Firefox".
2. **No single client wins.** `curl_cffi` (Chrome TLS impersonation) unblocks
   MDPI/PMC/Springer but is *itself* blocked by SAGE, which plain `requests`
   handles. Review Buddy therefore uses a **dual transport** that retries with
   the other client on a block (`src/searchers/http_client.py`).
3. **Rate limiting.** Zotero paces requests per domain with backoff. A parallel
   downloader that hammers a publisher earns an IP block that lasts hours — and
   then looks exactly like "this tool can't download that paper". We hit this
   with SAGE mid-benchmark. Review Buddy now implements the same per-domain
   throttle (`DomainThrottle`), exempting high-volume APIs like `doi.org`.
4. **Session/cookies.** The app carries your browser session and any library
   proxy (EZproxy). IP-based campus access works for a script; cookie-based
   login does not.

### Practical implication (updated: this gap is now closed)

The remaining gap really was a browser-engine gap, not a translator gap — so we
closed it by driving a real browser: `src/searchers/browser_fetcher.py`,
described in detail below. Short version: a real Gecko engine alone wasn't
enough either (see "Why Firefox alone still wasn't enough"); the actual fix
needed one more layer.

## Measured results

123 DOIs from a real single-trial-EEG search, on a university network,
`scripts/benchmark_zotero_ab.py`:

| Configuration | PDFs retrieved | Time |
|---|---|---|
| Built-in chain only | 41/123 (33%) | 34s |
| **+ Zotero resolver chain** | **48/123 (39%)** | 65s |

Success by publisher (Zotero chain):

| Publisher | Retrieved | Note |
|---|---|---|
| Springer | 8/8 | ✅ |
| Frontiers | 11/12 | ✅ |
| PLOS | 3/3 | ✅ |
| IOP | 2/2 | ✅ |
| SAGE | 4/7 | partial |
| MDPI | 2/8 | Cloudflare |
| Wiley | 0/9 | Cloudflare |
| **Elsevier** | **4/49** | **Cloudflare — the bottleneck** |

**Elsevier alone accounts for 45 of the 75 failures.** After the dual transport
and throttling fixes, outright `403`s fell to 13; the dominant failure is now
"fetched something that isn't a PDF" (33) — i.e. a paywall or landing page
returned instead of the file.

### Elsevier at scale: the browser is the mechanism, not the fallback

The 4/49 above predates the browser fetcher. Re-measured on **100 Elsevier DOIs**
(prefix `10.1016`, drawn from a live Scopus search, 71 distinct journals,
2020–2026, capped 6 per journal), same set run twice on a university network
with `scripts/benchmark_publisher.py`:

| Configuration | Retrieved | Wall time | Per paper |
|---|---|---|---|
| HTTP chain + Zotero resolver | 14/100 (14%) | 2.2 min | 1.3s |
| **+ Camoufox browser fetcher** | **90/100 (90%)** | 14.2 min | 8.5s |

Strategy that won each paper in the full run: browser 77, Zotero resolver 11,
Unpaywall 2. So every HTTP-based strategy combined accounts for 13 papers in
100, and the browser for 77 more — on this publisher the browser is doing
essentially all of the work.

Two things follow. First, the 14% floor confirms the original diagnosis: this is
bot-blocking, not a resolver gap, because the resolver chain finds the links
fine and then cannot fetch them. Second, the browser stays **last** in the chain
despite winning most Elsevier papers, because it is ~6x slower per paper and the
cheaper strategies win outright on open-access publishers.

The remaining 10 failures were subscription content outside the account's
entitlement — no fetcher resolves those.

The remaining gap is therefore concentrated almost entirely on
Cloudflare-protected publishers (ScienceDirect, Wiley, MDPI). Recovering those
requires a real browser engine, not more resolvers.

### Benchmark methodology warning

Publisher rate limits contaminate repeated runs. Mid-testing, SAGE IP-blocked us
after two back-to-back 123-paper runs, and a *plain* `requests` client that had
previously succeeded started returning 403 — which initially looked like a
regression caused by the new transport. If you re-run the benchmark, space the
runs out and treat cross-run deltas of a few papers as noise.

## Closing the gap: a real browser (`src/searchers/browser_fetcher.py`)

Elsevier at 4/49 meant the resolver chain alone couldn't reach parity. The next
question was direct: is a real browser *actually* enough, or is there something
else going on? We tested this empirically rather than assuming.

### Attempt 1: stock Playwright Firefox — still blocked

A real Gecko engine, driven via Playwright, both headed and headless:

```
status: 403, title: "Just a moment...", body: "Are you a robot? Please
confirm you are a human by completing the captcha challenge below."
```

Waiting 20 seconds did not help — this is Cloudflare's *interactive* challenge,
not the auto-passing JS proof-of-work variant. So "it's a real browser" was not
sufficient by itself. Why?

```js
// evaluated in the Playwright-driven page:
navigator.webdriver  // → true
```

**`navigator.webdriver` is `true` for every WebDriver-based automation tool** —
Playwright, Selenium, Puppeteer — because that flag is literally how the
remote-control protocol identifies itself; it's part of the W3C WebDriver spec.
Cloudflare checks it directly. This is not a fixable-by-better-Firefox problem:
it's structural to *how* the browser is being driven, independent of engine.

Zotero doesn't trip this because it isn't "automating" a browser via a remote
protocol at all. It embeds Gecko directly as a library inside its own
application code (the XULRunner architecture) — there's no separate automation
layer to announce itself.

### Attempt 2: Camoufox — a patched Firefox that hides the tell

[Camoufox](https://github.com/daijro/camoufox) is a maintained, patched Firefox
build built specifically to remove WebDriver/automation fingerprints (plus
canvas, WebGL, font, and screen-noise fingerprinting) while still exposing a
standard Playwright `BrowserContext`/`Page` API — so it's a near drop-in
replacement for the code in `browser_fetcher.py`.

```
stock Playwright Firefox:  navigator.webdriver → True
Camoufox:                  navigator.webdriver → False
```

**Verified working end-to-end**: MDPI, a Cloudflare-protected open-access
publisher, via the full `BrowserFetcher` class (real DOI → doi.org redirect →
Cloudflare → citation_pdf_url/download-link extraction → save):

```
MDPI (fresh domain) via BrowserFetcher: success=True in 16.2s, 324350 bytes
```

### The remaining variable: IP reputation, not fingerprinting

Re-testing the *same* Elsevier DOI after switching to Camoufox: still
challenged. This is a **separate, second factor** from the fingerprint issue,
and testing isolated it cleanly:

- A **fresh, never-before-touched** Elsevier DOI got the same challenge as the
  one we'd hit repeatedly — ruling out per-article caching.
- Wiley, hit far less during benchmarking than Elsevier, showed a *different*,
  lighter Cloudflare message ("Performing security verification" vs Elsevier's
  explicit "complete the captcha challenge") — consistent with a
  request-volume-driven trust score rather than a permanent per-publisher wall.

In short: **this session's own benchmarking — three full 123-paper runs plus
assorted probes, all hitting sciencedirect.com/onlinelibrary.wiley.com from one
IP within about an hour — plausibly used up that IP's trust budget with
Cloudflare for those two domains specifically.** That is not the same as "the
approach doesn't work"; it's the cost of the *testing method itself* looking
like an attack. A human using Zotero occasionally, a handful of papers at a time,
doesn't generate that pattern.

**This is exactly what `scripts/browser_login.py` is for.** Cloudflare's
interactive challenge needs an actual human click/solve — something no
automation tool, including this one, can do for you. Run it once, headed:

```bash
python scripts/browser_login.py
```

Solve the CAPTCHA yourself for each publisher tab that shows one. The resulting
`cf_clearance` cookie is saved in the persistent Camoufox profile
(`.browser_profile/`) and should let subsequent **headless** automated fetches
through for a while, since they now carry a browser fingerprint + IP + cookie
combination Cloudflare has already vetted.

### Attempt 3: a direct deep-link looks like a bot even with a clean session

After the login script (`scripts/browser_login.py`) was actually run, Elsevier
was still challenged on a direct `doi.org` link — even with an authenticated
session and a fingerprint-clean browser. Comparing a bare deep-link against a
session that had just visited the homepage isolated the real trigger:

```
direct deep-link to article:          Cloudflare interactive CAPTCHA
homepage visit, THEN the same link:   passes cleanly, real article loads
```

**Jumping straight to `/science/article/pii/...` without ever visiting the
site is itself a bot signal** — that is exactly the access pattern a scraping
tool has, and exactly what natural browsing never looks like. `browser_fetcher.py`
now does this automatically: after a navigation lands, if the page shows a
challenge title, it warms up by visiting the bare origin of the *actual final*
domain (not the original URL's domain — a chain like `doi.org →
linkinghub.elsevier.com → www.sciencedirect.com` means the domain that needs
warming up is only known after the redirect resolves) and retries.

**A second wrinkle**: that redirect chain can finish at an unpredictable time —
sometimes under a second, sometimes several — so a query issued right after a
fixed wait can hit `Execution context was destroyed, most likely because of a
navigation` if a hop is still in flight. This turned out to be exactly as
useful a "we're not settled yet" signal as the challenge title, so both paths
now trigger the same warm-up-and-retry, with the actual final URL obtained by
polling until it stops changing rather than trusting a single fixed-duration wait.

**A third wrinkle, specific to Elsevier**: the PDF itself is served from a
separate CDN subdomain (`pdf.sciencedirectassets.com`) as a presigned,
time-limited URL, guarded by its own JS-executed check. A real Camoufox page
navigation passes it automatically; a plain follow-up HTTP request
(`APIRequestContext.get()`) to that same resolved URL does **not** — it has no
JS engine, so it gets a "Security verification" page instead of the PDF bytes.
The fix: open the PDF link in a **new page** within the same session (not by
clicking — Playwright's synthetic click hung indefinitely on ScienceDirect's
floating "View PDF" button, a fixed-position element its actionability checks
never consider stable) and capture the actual PDF bytes via a `response`
listener as they stream through that page's own successful navigation, rather
than re-fetching the resolved URL separately.

### Validated results

12 fresh DOIs (never touched by any prior test in this investigation), spanning
Elsevier, Wiley, MDPI, and Frontiers, run through the real `PaperDownloader`
pipeline (`use_zotero=True, use_browser=True`, 2 parallel workers):

| Metric | Result |
|---|---|
| Overall | **8/12 (67%)** |
| By method | Zotero resolver chain: 3 · Browser fetcher: **5** |
| Wiley | **3/3** (was 0/9 in the original 123-paper benchmark) |
| Elsevier | **2/3** (was 4/49, ~8%, in the original benchmark) |
| Frontiers | 2/3 (1 miss was a conference abstract with no full PDF to find) |
| MDPI | 1/3 |

The browser fetcher — Camoufox + homepage warm-up + redirect-aware retry +
new-page PDF capture — is directly responsible for 5 of the 8 successes here,
recovering papers the Zotero/HTTP resolver chain alone could not.

**Caveat on reproducibility**: rapid, repeated single-DOI testing against the
*same* article during development sometimes re-triggered the challenge even
after these fixes — consistent with Cloudflare's bot score responding
adaptively to request *volume and pattern*, not just a one-time fingerprint or
cookie check. A realistically-paced run (one paper at a time, spread across a
normal download session, as the pipeline naturally does) is the fair test, not
a debugging loop that hits the same URL a dozen times in a few minutes.

### How it's wired into the downloader

`use_browser=True` (opt-in — needs `camoufox fetch` and, for a currently-flagged
IP, the login step above) adds it in two places in `_resolve_and_download`:

- **Fast path** (step 0.5): if the paper's URL matches a known
  Cloudflare-protected domain (`KNOWN_BROWSER_REQUIRED_DOMAINS` — currently
  ScienceDirect, Wiley, MDPI, based on the measured breakdown above), the
  browser fetcher is tried immediately, skipping HTTP strategies known to be
  doomed for that domain.
- **Last resort** (step 4.7): for everything else, only after every cheaper
  HTTP strategy has failed — launching and driving a browser is far slower
  than an HTTP request (~2–16s vs milliseconds), so it should never run for a
  paper a fast method would have solved anyway.

The browser itself runs on **one dedicated background thread** (Playwright's
sync API isn't safe to share across threads), with worker threads submitting
requests through a queue and blocking on a future — this also means browser
actions are naturally serialized, which is the safer behavior for the exact
IP-reputation reason above: one action at a time looks far less like an attack
than N parallel tabs hammering the same publisher.

### Why it's slow — and the "season once" fix (matching Zotero's speed)

The honest cost picture, per paper:

| Paper kind | Path | Time |
|---|---|---|
| Open-access / preprint | HTTP resolver chain | ~1–3s (browser never runs) |
| Hard publisher, **first** of its domain this session | browser + warm-up | ~11–18s |
| Hard publisher, **subsequent** on same domain | browser, seasoned | ~7s |

Zotero *feels* instant on hard papers for one reason: its embedded browser is a
long-lived, deeply-seasoned session that already holds a valid `cf_clearance`
cookie, so Cloudflare never challenges it — it loads the article and grabs the
PDF with no anti-bot detour. Our cold session pays that detour (visit homepage
→ re-navigate → capture) the *first* time it meets a domain.

`browser_fetcher.py` closes most of that gap with **`_warmed_origins`**: the
homepage warm-up banks a `cf_clearance` cookie in the persistent context, so it
is done **once per domain per session**. Every later paper on that domain loads
its article directly, exactly like Zotero. Measured on three sequential MDPI
papers: 11.2s (first, includes warm-up) → 6.8s → 7.5s, all successful (MDPI went
from 1/3 to **3/3** with this plus the faster capture below).

Two other speedups: the PDF is captured by polling a `response` listener and
returning the instant the bytes arrive (was a `networkidle` wait that blocks
until *all* network stops — slow, and never truly idle for a PDF viewer); and
`03_download_papers.py`'s summary now reports **average time per method**, so
the cost is visible rather than guessed at.

The residual gap to Zotero (our ~7s vs its ~2–3s) is inherent to a *batch* tool
vs a *warm resident app*: Zotero's session has weeks of cookies; ours seasons
per run. In the dimension that matters for a systematic review, we can be
*better* — an unattended parallel run over a whole `.bib` of hundreds of papers,
which the GUI doesn't do.

## References (Zotero source)

- `chrome/content/zotero/xpcom/attachments.js` — `getFileResolvers()`, `addFileFromURLs()`
- `chrome/content/zotero/xpcom/utilities_internal.js` — `getOpenAccessPDFURLs()`, `getFileFromDocument()`
- [Camoufox](https://github.com/daijro/camoufox) — the patched Firefox used by `browser_fetcher.py`
