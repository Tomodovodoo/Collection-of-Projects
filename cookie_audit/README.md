# Cookie Audit NL

**Evidence-first, reproducible research into cookie-consent choices on websites serving the Netherlands.**

This repository contains a browser scanner, seed list and a GitHub Pages dashboard. It does **not** certify legal compliance and should not be used to publish allegations without manual review of the evidence.

**Current state:** The included candidate list is **not yet scanned**. Its initial results intentionally contain only `unknown` (`~`) values. No company is marked as violating the law based on user reports or historic screenshots alone.

## Legal scope

The Dutch Autoriteit Persoonsgegevens (AP) says that where consent for tracking is required, accepting and rejecting must be on the same consent layer; refusal must be clear, visible, and not require more clicks. Their guidance also covers fingerprinting, local storage, tracking pixels, and similar techniques. Consent is not required for strictly necessary storage or qualifying low-impact analytics, so "has cookies" **does not mean** "must have a consent banner".

Authoritative sources:

- AP: https://autoriteitpersoonsgegevens.nl/themas/internet-slimme-apparaten/cookies/heldere-en-misleidende-cookiebanners
- AP: https://autoriteitpersoonsgegevens.nl/themas/internet-slimme-apparaten/cookies/trackingcookies
- AP enforcement announcement (16 Oct 2026): https://autoriteitpersoonsgegevens.nl/actueel/ap-onderzoekt-websites-vanwege-misleidende-cookiebanner
- Dutch Telecommunications Act, Article 11.7a, and GDPR consent provisions.

Scope is not just `.nl` domains: it depends on whether the rules apply to a website/service and to the tracking of users in the Netherlands. This is a technical screening project, not legal advice.

## Install

Requires Python 3.11+ (tested with Python 3.13) and approximately 2–4 GB available space for browser installation and a thousand local screenshots.

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
python -m playwright install chromium
```

## Run a sample

```bash
python audit.py --targets config/seed_sites.csv --limit 12 --concurrency 4
python export.py --targets config/seed_sites.csv --results results
python -m http.server 8000 -d docs
# Visit http://localhost:8000
```

The scanner uses isolated Chrome/Chromium contexts with Netherlands locale/timezone, mobile and desktop viewport profiles, waits for delayed banners, inspects frames and open shadow roots, photographs the initial state, attempts a rejection, revisits the page, and tracks selected known collection endpoints plus tracker-like cookie names. Each per-device output goes to `results/`; screenshots go to `evidence/`. Both are excluded from Git commits by default.

Flags:

```bash
python audit.py --targets config/top1000.csv --limit 1000 --viewports mobile,desktop --concurrency 5
python audit.py --targets config/top1000.csv --limit 1000 --viewports desktop --headful --force
```

- `--concurrency`: parallel sites, default 5. Higher values may trigger throttling or require more RAM.
- `--wait-ms`: time to wait for delayed consent UI after DOM content loads, default 1800.
- `--timeout-ms`: page timeout, default 22000.
- `--headful`: use an ordinary visible Chromium window to compare against headless behavior.
- `--force`: overwrite existing results. Without it, the crawler resumes by skipping existing per-domain/per-viewport result files.

This does **not** evade CAPTCHAs, access restrictions, or anti-bot protections. Such results are `unknown`; don't silently substitute a different page state.

## Select your top 1,000 targets

**Preferred:** use the [NetAPI country-specific top-1,000 list](https://netapi.com/top-websites/nl/) (visitors **in** the Netherlands, including `.com` and `.nl` domains). NetAPI publishes a free list based on CrUX country popularity groups, with ordering within groups inferred from additional signals; the ranking is not exact site traffic measurement. Its country list and API are published under CC BY 4.0, with attribution to [NetAPI](https://netapi.com/). The API is public but its exact response schema has not been live-tested from this environment.

```bash
python generate_targets.py --netapi-nl --out config/top1000.csv --limit 1000
```

Or download the CSV from the NetAPI country page and pass it directly; the generator accepts both `Domain,NetAPI_Rank_NL` and `domain,rank` headers:


```bash
python generate_targets.py --ranking-csv my_netherlands_site_ranking.csv --out config/top1000.csv --limit 1000
```

**Proxy only:** download the Tranco global ranking and select the first 1,000 `.nl`/`.amsterdam` entries. This is **not** the 1,000 most visited websites in the Netherlands; many high-traffic `.com` domains are omitted. It is a useful locally reproducible candidate generator if you have no country-specific ranking:

```bash
python generate_targets.py --tranco-nl --out config/top1000.csv --limit 1000
```

A country ranking with 1,000 rows can yield **fewer than 1,000 non-NSFW candidates** after exclusions; do not fill the missing slots with invented ranks. The hostname/category filter excludes obvious adult domains, but automated filtering alone cannot guarantee a completely non-NSFW list. Review the CSV manually before public use. Operator mapping requires verified ownership data; the seed CSV contains examples, but generated targets default to `Unknown`.

## What the columns mean

| Check | Pass (`✓`) | Flag (`✕`) | Unknown (`~`) |
|---|---|---|---|
| Reject available | A reject option was found and clicked | Reserved for confirmed absence | Unable to verify rejection path |
| Same layer | Direct reject and accept on initial consent layer | Only accept found on the initial layer | Banner/accept could not be found |
| Equal clicks | Rejection takes no more clicks | Verified rejection needs more clicks | Steps could not be verified |
| Visible reject | Both controls reasonably prominent | Reject hidden/offscreen/text-link/tiny | Insufficient visual information |
| Before consent | No listed tracker indicators observed | Known collection endpoint or tracker-like cookie observed | Scan was blocked/failed |
| After rejection | Same after rejecting and reloading | Indicators persisted after reject | Rejection not verified or scan failed |

The `noTracking...` columns are **narrow technical observations**, not exhaustive or legal determinations. A green check does not exclude first-party analytics, server-side forwarding, service-worker behavior, fingerprinting, tracking via unknown hosts, or other unobserved scenarios. A red flag does not by itself prove the processing requires consent; exemptions, cookieless pings, and data flow need manual review.

The dashboard scores **weighted potential issues** (pre-consent/after-reject = 5, reject visible/same layer/reject available = 3, extra clicks = 2) and sorts by most negative technical checks. The operator view aggregates those flags; it is not a legal operator-level judgment.

## Suggested validation before large-scale publication

1. Manually label at least 100–200 representative live sites with screenshot evidence, including non-consent sites, blocked sites, paywalls, iframes, and difficult CMPs.
2. Measure **precision, recall, and false-positive rate by check**, not one blended accuracy number. Tune thresholds against a validation set that wasn't used for development.
3. Compare mobile and desktop, fresh contexts and revisits, clean traffic and bot-blocked states, and different geo-IP exits. A Dutch timezone is **not** a Dutch IP address.
4. For tracking flags, inspect the actual request payload and cookie classification before making a public legal assertion.
5. Allow operators to submit corrections with reproducible evidence, preserve scan timestamps, and avoid automatically presenting unreviewed red flags as legal findings.

## Data privacy and safe publication

Raw browser captures can contain location, identifying tokens, consent identifiers, personalized content, and copyrighted snippets. Network URLs are stripped of query strings and fragments. JSON exports do not include cookie values. The `results/` and `evidence/` directories are gitignored; review any evidence before sharing publicly.

For production use, add a separate browser-navigation pass for each manual scenario and per-site rate limiting. Respect website rules and do not attempt to bypass access controls. Exclude login-only flows or anything requiring private credentials.

## Existing work

- [CookieAudit (ETH Zürich)](https://github.com/SzymonNastaly/CookieAudit)
- [CookieEnforcer (Google Research)](https://research.google/pubs/cookieenforcer-automated-cookie-notice-analysis-and-enforcement/)
- [ConsentCrawl](https://github.com/dumkydewilde/consentcrawl)
- [OpenWPM](https://github.com/openwpm/OpenWPM) for more exhaustive browser instrumented tracking measurement

## Deploy to GitHub Pages

For the exact address `https://USERNAME.github.io/cookie_audit/`, create a **public repository named `cookie_audit`**, push this project to `main`, and select **Settings → Pages → Build and deployment → GitHub Actions**. The included workflow `.github/workflows/pages.yml` deploys `docs/` on each push.

A regular repository named `OTHER_NAME` will have a different path, even if this project is in a `cookie_audit/` subdirectory. GitHub Pages deployment must be enabled by the repository owner before it appears publicly.

`docs/data/results.json` is initially generated from the 12 example targets, all `~` until real runs are completed. After scans, `python export.py` refreshes it. The dashboard has search, responsive tables, per-check explanations, operator groups, and CSV download.

## Tests

```bash
PYTHONPATH=. python -m pytest -q
```

The browser fixture tests verify DOM detection on a compliant banner, extra rejection click, visually buried rejection link, and no-banner case. This test suite is **not** a 1,000-site accuracy benchmark; live-site testing is required for claims of high precision.

MIT License; see `LICENSE`.