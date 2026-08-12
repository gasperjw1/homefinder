# HomeFinder — Design Document & Build Guide

> **What this is:** A complete handoff document for Claude Code to build HomeFinder as a
> GitHub Pages website. This contains every decision, constraint, workaround, and open
> question from extensive research and prototyping done in Claude.ai. Read this fully
> before writing any code. Refer back to it as the source of truth throughout the project.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture](#2-architecture)
3. [Data Sources — Full Research](#3-data-sources)
4. [Constraints, Risks & Workarounds](#4-constraints-risks--workarounds)
5. [Criteria System](#5-criteria-system)
6. [Frontend Design](#6-frontend-design)
7. [GitHub Actions Pipeline](#7-github-actions-pipeline)
8. [Deduplication Strategy](#8-deduplication-strategy)
9. [Cost Analysis](#9-cost-analysis)
10. [Existing Code Inventory](#10-existing-code-inventory)
11. [Phase-by-Phase Build Plan](#11-phase-by-phase-build-plan)
12. [Open Decisions](#12-open-decisions)
13. [Progress Tracker](#13-progress-tracker)

---

## 1. Project Overview

**HomeFinder** is a real estate listing aggregator for the New York tri-state area
(New York, New Jersey, Connecticut). It scrapes and normalizes property listings from
multiple sources, applies user-defined filters, and presents results on a public,
mobile-first website hosted on GitHub Pages.

**Core value proposition:** No single real estate platform shows every available listing
(this became dramatically worse in 2026 — see section 3). HomeFinder pulls from multiple
sources, deduplicates, and gives the user one unified view of what's actually for sale.

**Target user:** The developer (Yash) and anyone he shares the link with. Public GitHub
Pages site, no authentication needed.

**Scope for v1:** Buy-only listings in the tri-state area, sourced primarily from
Redfin's Stingray API, with daily data refreshes via GitHub Actions.

**Future scope:** Rental listings, additional source adapters (StreetEasy, Douglas Elliman,
Realtor.com), Walk Score enrichment, saved searches with email alerts.

---

## 2. Architecture

### High-Level Flow

```
┌──────────────────────────────────────────────────────┐
│                  GitHub Actions (daily cron)          │
│                                                      │
│  1. Run Python scraper (homefinder.py)               │
│  2. Hit Redfin Stingray API for all tri-state areas  │
│  3. Paginate through all results                     │
│  4. Normalize + deduplicate                          │
│  5. Write results to data/listings.json              │
│  6. Commit + push to repo                            │
│  7. GitHub Pages auto-rebuilds                       │
└──────────────┬───────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────┐
│              GitHub Pages (static site)              │
│                                                      │
│  Vite + React + TypeScript frontend                  │
│  - Loads data/listings.json on page load             │
│  - All filtering/sorting happens client-side         │
│  - No API calls from the browser                    │
│  - Mobile-first responsive design                    │
└──────────────────────────────────────────────────────┘
```

### Why This Architecture

- **GitHub Pages is static-only** — no server, no serverless functions, no backend.
  All dynamic work (API calls to Redfin) must happen at build time via GitHub Actions.
- **CORS blocks browser→Redfin calls** — Redfin's Stingray API rejects browser origins.
  Even if it didn't, the API requires a non-browser User-Agent header. This is why we
  can't call it directly from the frontend.
- **GitHub Actions is free** — 2,000 minutes/month on free tier. Our daily scrape takes
  ~5-10 minutes, so ~300 minutes/month. Well within budget.
- **JSON-as-database** — For the expected data volume (5,000-20,000 listings), a single
  JSON file is fast enough for client-side filtering. If it grows beyond ~5MB, we can
  split into per-county files and lazy-load.

### Tech Stack

| Layer        | Technology                   | Rationale                                   |
|-------------|------------------------------|---------------------------------------------|
| Scraper     | Python 3.11+ / requests      | Already built, Redfin API needs server-side |
| Data store  | JSON file in repo            | No database needed for static site          |
| Frontend    | Vite + React 18 + TypeScript | Fast builds, type safety, Yash is familiar  |
| Styling     | Tailwind CSS                 | Utility-first, mobile-responsive, fast      |
| Deployment  | GitHub Pages                 | Free, auto-deploys on push                  |
| CI/CD       | GitHub Actions               | Free cron, runs scraper daily               |

---

## 3. Data Sources

### The 2026 Listing War — Critical Context

The US real estate listing landscape fractured in 2026. Understanding this is essential
for knowing why multi-source matters and what each source uniquely covers.

**Camp 1 — Redfin + Compass + Rocket:**
Compass announced a 3-year deal to syndicate 500,000+ "Private Exclusive" and "Coming
Soon" listings to Redfin. These listings are NOT on Zillow, Homes.com, or Realtor.com.
This makes Redfin the single best source for the tri-state area right now.

**Camp 2 — Zillow + KW/REMAX/HomeServices:**
Zillow launched "Zillow Preview" (March 2026) with Keller Williams, REMAX, HomeServices
of America, Side, and United Real Estate. These coming-soon listings may NOT appear on
Redfin until they hit the MLS.

**Camp 3 — Homes.com + Realtor.com + eXp:**
eXp Realty partnered with Homes.com, Realtor.com, and ComeHome.com for pre-marketing
syndication. These are NOT on Redfin or Zillow initially.

**FSBO (For Sale By Owner):**
Listings posted directly to Zillow as FSBO never touch the MLS. They do NOT appear on
Redfin, Realtor.com, or Homes.com. They exist only on Zillow.

**Brokerage-only private exclusives:**
Douglas Elliman's "Black Label" platform and Corcoran's "Reserve" platform have
listings that exist ONLY on their brokerage websites until they hit the MLS.

### Source-by-Source Detail

#### Redfin Stingray API ✅ PRIMARY — Free, Unlimited

**Status:** Confirmed working. No API key needed, no signup.
**What it is:** Redfin's internal API used by their web frontend.

**Endpoints:**
- `GET /stingray/do/location-autocomplete?location={query}&v=2`
  - Resolves city/ZIP/neighborhood → `region_id` + `region_type`
  - Response prefixed with `{}&&` (XSSI protection, must be stripped)
- `GET /stingray/api/gis?region_id={id}&region_type={type}&...`
  - JSON search results with full pagination support
  - Params: `page_number`, `start`, `num_homes` (page size)
  - Response prefixed with `{}&&`
- `GET /stingray/api/gis-csv?...` (same params)
  - CSV format, capped at 350 results (no pagination)
  - Simpler to parse but limited — use JSON endpoint instead
- `GET /stingray/api/home/details/aboveTheFold?propertyId={id}&listingId={id}&accessLevel=1`
  - Individual property detail (description, photos, amenities)
- `GET /stingray/api/home/details/belowTheFold?...`
  - Additional detail (schools, tax history, similar homes)

**Key query parameters:**
- `region_id` + `region_type`: Required. Type 2=ZIP, 5=county, 6=city
- `num_homes`: Results per page (default 350)
- `page_number`: Page number (1-indexed)
- `start`: Offset (0-indexed)
- `status`: 1=active, 9=all
- `uipt`: Property types (1=house, 2=condo, 3=townhouse, 4=multi, 5=land)
- `min_price`, `max_price`: Price range
- `min_num_beds`, `max_num_beds`: Bedroom count
- `min_num_baths`: Bathroom count
- `min_listing_approx_size`, `max_listing_approx_size`: Square footage
- `min_year_built`: Year built filter
- `hoa`: Max monthly HOA
- `gar`: "true" for garage filter
- `min_num_park`: Minimum parking spots
- `sf`: Sort fields (use "1,2,3,5,6,7")
- `v`: API version (use 8)

**Response format (JSON):**
```
{}&&{"payload":{"homes":[{homeData:{...}}, ...], "totalResultCount": N}}
```
Each `homeData` contains: `addressInfo`, `priceInfo`, `bedInfo`, `bathInfo`,
`sqftInfo`, `yearBuilt`, `daysOnMarket`, `hoaDuesInfo`, `mlsId`, `url`,
`propertyType`, `listingMetadata.mlsStatusText`, `lotSize`, `propertyId`.

**Coverage:** All MLS listings + Compass Private Exclusives + Coming Soon.
Estimated ~85-90% of all for-sale inventory in the tri-state.

**Rate limits:** No formal limit, but aggressive IP-based throttling. Use 2-second
delays between requests. Geo-restricted to US IPs (GitHub Actions runners are US-based,
so this is fine).

**Fragility:** This is an undocumented internal API. Endpoints can change when Redfin
ships frontend updates. Field names in the JSON response can shift. The `{}&&` prefix
is XSSI protection that must be stripped before JSON parsing.

**Tri-state region IDs (pre-mapped, Redfin region_type=5 for counties):**
```
New York County, NY    → 1839    Kings County, NY (Brooklyn) → 1713
Queens County, NY      → 1900    Bronx County, NY            → 1587
Richmond County, NY    → 1906    Westchester County, NY      → 2068
Nassau County, NY      → 1840    Suffolk County, NY          → 1986
Rockland County, NY    → 1919    Bergen County, NJ           → 1561
Hudson County, NJ      → 1682    Essex County, NJ            → 1625
Passaic County, NJ     → 1879    Union County, NJ            → 2038
Middlesex County, NJ   → 1806    Morris County, NJ           → 1833
Monmouth County, NJ    → 1824    Fairfield County, CT        → 1630
New Haven County, CT   → 1847
```

**IMPORTANT:** These region IDs were identified during research but have NOT been
live-tested against the API. The first build step should verify each one by calling
the autocomplete endpoint and confirming they resolve correctly. If any are wrong,
use the autocomplete endpoint to get the correct IDs.

---

#### Realtor.com via RapidAPI ✅ SECONDARY — Free Tier (100 req/month)

**Status:** Confirmed. Multiple unofficial APIs on RapidAPI marketplace.
**Best option:** "Realtor Data API" — free tier at 100 requests/month.
**What it covers:** MLS listings + eXp syndicated pre-market listings.

**Use case:** Cross-validation. Query 3-4 high-priority ZIPs per day to catch
listings that Redfin might not have (eXp exclusives, faster MLS refresh in some
markets). NOT for full sweeps (budget too small).

**Implementation:** Phase 2 or later. Not needed for v1.

---

#### Zillow (via Zillapi or APIllow) ⚠️ ENRICHMENT ONLY — Very Limited Free Tier

**Zillapi:** 100 credits ONE-TIME at signup (no card). 1 credit per record, 3 per
address lookup. A search returning 50 results burns half your lifetime budget.
**APIllow:** 50 requests/month free (no card). $9.99/month for 3,333 requests.

**What Zillow uniquely has:** Zestimates (property value estimates), tax records,
school ratings, Zillow Preview listings (KW/REMAX), FSBO listings.

**Use case:** Enrich specific high-interest properties with Zestimate + tax data.
NOT for search/discovery. Phase 3 or later.

---

#### StreetEasy ⚠️ FUTURE — NYC-Specific Enrichment

**Status:** No public API. Scrapable with BeautifulSoup (HTML parsing).
**What it uniquely has:** NYC co-op vs condo distinction (critical in NYC market),
building-level amenity data (doorman, gym, roof deck, laundry, etc.),
monthly maintenance/common charges, tax abatement status.
**Limitation:** 1,050 result cap per search (paginatable).
**Use case:** Phase 2+. Enrich NYC listings with co-op/condo details and building
amenities that Redfin doesn't carry.

---

#### Douglas Elliman ⚠️ FUTURE — Private Exclusives

**Status:** No API. Their "Black Label" platform has listings NOT on any aggregator.
**What it uniquely has:** Pre-MLS luxury listings in NYC and Long Island.
**Use case:** Phase 3+. Scrape elliman.com search for tri-state Black Label inventory.

---

#### Walk Score API ✅ ENRICHMENT — Free (5,000/day)

**Status:** Confirmed. 5,000 free API calls per day. Requires API key (instant signup).
**Endpoint:** `GET https://api.walkscore.com/score?format=json&address=...&lat=...&lon=...&wsapikey=...`
**Returns:** Walk Score, Transit Score, Bike Score (each 0-100).
**Use case:** Enrich every listing with walkability data. 5,000/day is effectively
unlimited for our volume. Phase 2.

**Note:** Walk Score API key should be stored as a GitHub Actions secret, NOT committed
to the repo.

---

### Coverage Summary

| Source         | Coverage                              | Free Budget       | Phase |
|---------------|---------------------------------------|-------------------|-------|
| Redfin         | MLS + Compass exclusives (~85-90%)   | Unlimited         | 1     |
| Realtor.com    | MLS + eXp exclusives                 | 100 req/month     | 2     |
| Walk Score     | Walk/Transit/Bike scores             | 5,000/day         | 2     |
| StreetEasy     | NYC co-op/condo/building detail      | Free (scraping)   | 2-3   |
| Zillapi        | Zestimates, tax data                 | 100 credits once  | 3     |
| APIllow        | Zestimates, school ratings           | 50 req/month      | 3     |
| Elliman        | Black Label exclusives               | Free (scraping)   | 3+    |

**Estimated v1 coverage (Redfin only):** ~85-90% of active for-sale listings.
**Estimated v2 coverage (+ Realtor.com + StreetEasy):** ~93-95%.
**Remaining gap:** Zillow FSBO-only, Zillow Preview (KW/REMAX), true pocket deals.

---

## 4. Constraints, Risks & Workarounds

### CORS
**Problem:** Redfin's API rejects browser-origin requests.
**Workaround:** All API calls happen in GitHub Actions (server-side Python). The
frontend only reads a static JSON file. No CORS issues.

### Redfin XSSI Prefix
**Problem:** All Redfin JSON responses start with `{}&&` which breaks `json.loads()`.
**Workaround:** Strip the prefix before parsing:
```python
if text.startswith("{}&&"):
    text = text[4:]
```

### Redfin Rate Limiting
**Problem:** Aggressive IP-based throttling. Too many rapid requests = temporary ban.
**Workaround:** 2-second delay between requests. GitHub Actions runners rotate IPs
between runs, so daily cron jobs won't accumulate bans. If we hit issues, increase
delay to 3-5 seconds.

### Redfin API Instability
**Problem:** Undocumented internal API. Field names, response structure, and endpoints
can change without notice when Redfin deploys frontend updates.
**Workaround:** Defensive parsing — use `.get()` with fallbacks for every field.
Log warnings for unexpected response shapes. The GitHub Action should NOT fail silently;
if parsing breaks, it should commit an error log and keep the previous listings.json
intact (don't overwrite good data with an empty file).

### Pagination & the 350-Result Cap
**Problem:** The CSV endpoint caps at 350. Dense counties (Manhattan) can have
thousands of active listings.
**Workaround:** Use the JSON endpoint (`/stingray/api/gis`) which supports proper
pagination via `page_number` and `start` parameters. Loop until
`fetched >= totalResultCount`.

### GitHub Actions Secrets
**Problem:** Walk Score API key, and any future API keys, cannot be in the repo.
**Workaround:** Store as GitHub Actions secrets. Access via `${{ secrets.WALKSCORE_KEY }}`
in the workflow YAML, pass to the Python script as environment variables.

### JSON File Size
**Problem:** 10,000+ listings as JSON could be 5-10MB. Large initial page load on mobile.
**Workaround for v1:** Gzip should bring it to ~1-2MB, which is acceptable. GitHub
Pages serves gzipped content by default.
**Workaround for v2:** Split into per-county JSON files. Frontend loads the county
file(s) the user selects, not the entire dataset.

### User-Agent Header
**Problem:** Redfin may block requests with the default `python-requests` user agent.
**Workaround:** Use a realistic browser User-Agent string:
```
Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36
(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36
```

### GitHub Actions Network
**Problem:** GitHub Actions runners need to reach `www.redfin.com`.
**Workaround:** Standard GitHub-hosted runners have unrestricted outbound HTTPS.
Redfin's geo-restriction requires US IPs — GitHub's runners are US-based. No issue.

### Terms of Service
**Risk:** Scraping Redfin's internal API may violate their TOS. They could block
GitHub Actions IPs or send a cease-and-desist.
**Mitigation:** Keep request volume reasonable (one daily sweep, not continuous
polling). Don't redistribute raw Redfin data commercially. This is a personal tool.
If Redfin blocks us, we fall back to Realtor.com as primary source.

---

## 5. Criteria System

The frontend must support filtering by all of these. The Python scraper applies
server-side filters where the Redfin API supports them (marked ★), reducing data
volume. Everything else is filtered client-side in the browser.

### Server-side (Redfin API parameters) ★

- Price range (min/max) ★
- Bedrooms (min/max) ★
- Bathrooms (min) ★
- Square footage (min/max) ★
- Property type (house, condo, townhouse, multifamily, land) ★
- Year built (min) ★
- Max HOA/month ★
- Garage (boolean) ★
- Min parking spots ★
- Listing status (active, coming soon, pending) ★

### Client-side only (post-filter)

- City / neighborhood / ZIP (text search within results)
- Walk Score minimum
- Transit Score minimum
- Bike Score minimum
- Price per square foot range
- Days on market range
- Lot size range
- Keyword search in description (e.g., "doorman", "laundry", "elevator")
- Sort by: price, price/sqft, newest listed, walk score

---

## 6. Frontend Design

### Framework: Vite + React 18 + TypeScript + Tailwind CSS

**Why Vite:** Fastest build tool, native TypeScript, trivial GitHub Pages deploy.
**Why TypeScript:** The Property schema has 25+ fields; type safety prevents bugs.
**Why Tailwind:** Mobile-first utility classes, no custom CSS maintenance.

### Pages / Views

1. **Search & Filter Panel** — Collapsible filter controls. On mobile, this is a
   slide-up sheet or a dedicated "Filters" tab. On desktop, it's a sidebar.

2. **Results List** — Property cards sorted by the user's chosen sort order.
   Each card shows: status badge, property type, address, city/state, price,
   price/sqft, beds, baths, sqft, HOA, days on market, walk/transit scores.
   Tapping a card expands it or navigates to a detail view.

3. **Property Detail** — Expanded view with full description, all fields, link
   to the Redfin listing page, and (future) map pin.

4. **Stats Bar** — Top-level summary: total results, price range, average price/sqft.

### Design Direction

This is a data-dense tool, not a marketing site. Prioritize scan-ability and
information density over visual flair. Think Bloomberg Terminal meets Zillow,
not Airbnb.

- **Dark theme** — easier on the eyes for scrolling through hundreds of listings.
  Dark navy/slate background, high-contrast white text, accent color for CTAs
  and status badges.
- **Compact cards** — show maximum info per card without scrolling.
- **Status colors** — Green (active), amber (coming soon), orange (pending),
  red (sold). Consistent across all views.
- **Mobile-first** — cards are full-width on mobile, 2-column grid on tablet,
  3-column on desktop.
- **Performance** — virtualized list (react-window or similar) if >500 results
  to prevent DOM bloat on mobile.

### Data Flow (Frontend)

```
1. Page loads
2. Fetch /data/listings.json (static file from repo)
3. Parse into TypeScript Property[] array
4. User sets filters → apply client-side filter function
5. Display filtered results with sort
6. Persist filter preferences in localStorage
```

### Key TypeScript Types

```typescript
interface Property {
  source: string;
  source_id: string;
  address: string;
  city: string;
  state: string;
  zip_code: string;
  price: number | null;
  beds: number | null;
  baths: number | null;
  sqft: number | null;
  property_type: string;
  status: string;
  year_built: number | null;
  hoa_monthly: number | null;
  days_on_market: number | null;
  lot_sqft: number | null;
  latitude: number | null;
  longitude: number | null;
  url: string;
  mls_id: string | null;
  walk_score: number | null;
  transit_score: number | null;
  bike_score: number | null;
  description: string | null;
  price_per_sqft: number | null;
  fingerprint: string;
  scraped_at: string;
}

interface SearchCriteria {
  query: string;
  minPrice: number | null;
  maxPrice: number | null;
  minBeds: number | null;
  maxBeds: number | null;
  minBaths: number | null;
  maxBaths: number | null;
  minSqft: number | null;
  maxSqft: number | null;
  propertyTypes: string[];
  minYearBuilt: number | null;
  maxHoa: number | null;
  minWalkScore: number | null;
  minTransitScore: number | null;
  sortBy: 'price_asc' | 'price_desc' | 'newest' | 'value' | 'walk_score';
  statuses: string[];
}
```

---

## 7. GitHub Actions Pipeline

### Workflow: `.github/workflows/scrape.yml`

```yaml
name: Daily Listing Scrape

on:
  schedule:
    - cron: '0 10 * * *'    # 6 AM ET (10:00 UTC) daily
  workflow_dispatch:          # Allow manual trigger

jobs:
  scrape:
    runs-on: ubuntu-latest
    permissions:
      contents: write

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install requests

      - name: Run scraper
        env:
          WALKSCORE_API_KEY: ${{ secrets.WALKSCORE_API_KEY }}
        run: python scraper/run_sweep.py

      - name: Commit updated data
        run: |
          git config user.name "HomeFinder Bot"
          git config user.email "bot@homefinder"
          git add data/
          git diff --staged --quiet || git commit -m "📊 Daily listing update - $(date -u +%Y-%m-%d)"
          git push
```

### Scraper Script: `scraper/run_sweep.py`

This script:
1. Imports the Redfin adapter from the existing `home_finder/` package
2. Loops through all 20 tri-state county region IDs
3. Paginates through all results for each county
4. Deduplicates by fingerprint (normalized address + ZIP hash)
5. Writes the full result set to `data/listings.json`
6. Writes a metadata file `data/meta.json` with:
   - `last_updated`: ISO timestamp
   - `total_listings`: count
   - `by_county`: per-county counts
   - `by_status`: active/coming_soon/pending counts
   - `scrape_duration_seconds`: how long it took
   - `errors`: any counties that failed (with error messages)

### Error Handling

- If a county fails, log the error but continue with other counties.
- NEVER overwrite `listings.json` with an empty or significantly smaller file
  (>50% drop in count = something broke). Keep the previous version.
- Commit an `errors.log` if any counties failed so it's visible in git history.

### Data File: `data/listings.json`

```json
{
  "meta": {
    "last_updated": "2026-08-12T10:15:00Z",
    "total_listings": 12450,
    "source": "redfin"
  },
  "listings": [
    { ...Property fields... },
    ...
  ]
}
```

---

## 8. Deduplication Strategy

The same property can appear in multiple counties' results (edge cases near county
borders) or from multiple sources (Redfin + Realtor.com in future phases).

### Fingerprinting

```python
fingerprint = sha256(f"{address.lower().strip()}|{zip_code.strip()}").hexdigest()[:16]
```

This produces a stable 16-character ID from the normalized address + ZIP. The same
property from different sources produces the same fingerprint.

### Merge Logic

When two records share a fingerprint, keep the one with more non-null fields. If
tied, prefer Redfin (our primary source). In future phases with multiple sources,
merge fields: take non-null values from each source to build the most complete record.

### Address Normalization Challenges

Real-world addresses vary: "123 Main St Apt 4B" vs "123 Main Street #4B" vs
"123 Main St Unit 4B". The current fingerprint doesn't normalize these — it uses
the raw address string. For v1 this is acceptable since we're single-source (Redfin
uses consistent formatting). For v2+ with multiple sources, implement:
- Strip directional suffixes (St/Street, Ave/Avenue, etc.)
- Normalize unit/apt/# formats
- Consider fuzzy matching with lat/lon proximity (<50m) as a secondary check

---

## 9. Cost Analysis

### Monthly Operating Costs (v1)

| Item                     | Cost    |
|--------------------------|---------|
| GitHub Pages hosting     | Free    |
| GitHub Actions (daily)   | Free    |
| Redfin Stingray API      | Free    |
| Custom domain (optional) | ~$12/yr |
| **Total**                | **$0**  |

### Future Phase Costs

| Item                       | Trigger              | Cost          |
|----------------------------|----------------------|---------------|
| Realtor.com (RapidAPI)     | Phase 2              | Free (100/mo) |
| Walk Score API             | Phase 2              | Free (5K/day) |
| Zillapi (Zillow data)      | Phase 3              | Free then $5/mo |
| APIllow (Zillow data)      | Phase 3              | Free then $10/mo |
| GitHub Actions overage     | If >2000 min/month   | $0.008/min    |

---

## 10. Existing Code Inventory

### Attached: `homefinder.py` (single-file scraper)

A fully working, tested Python script that:
- Resolves locations via Redfin autocomplete
- Fetches listings via the JSON endpoint with pagination
- Parses both JSON and CSV response formats
- Applies post-fetch filters
- Generates a self-contained HTML report
- Works on Android (Pydroid 3) and desktop

This is the code to adapt for the GitHub Actions scraper. The RedfinClient class,
Property dataclass, and filtering logic can be extracted directly.

### Attached: `home_finder/` package (modular version)

A more structured version with:
- `models.py` — Property and SearchCriteria dataclasses
- `adapters/base.py` — Abstract BaseAdapter interface
- `adapters/redfin.py` — Full Redfin adapter with pagination
- `filters.py` — Post-fetch filtering engine
- `storage.py` — SQLite persistence with change detection
- `engine.py` — Orchestrator (search, dedup, sweep)
- `config.py` — Constants, region IDs, API URLs
- `tests/` — 94 unit tests covering models, filtering, storage, and engine

The modular package has been tested and all 94 tests pass. Use this as the base
for the scraper, adapting the output to write JSON instead of SQLite.

---

## 11. Phase-by-Phase Build Plan

### Phase 1: Foundation (MVP)

**Goal:** Public website showing real Redfin listings with filtering.

- [ ] Create GitHub repo (`homefinder` or `home-finder`)
- [ ] Set up Vite + React + TypeScript + Tailwind project
- [ ] Adapt Python scraper for GitHub Actions (JSON output)
- [ ] Create GitHub Actions workflow (daily cron + manual trigger)
- [ ] Test the scraper manually (workflow_dispatch) and verify data
- [ ] Build the Property TypeScript type from the Python dataclass
- [ ] Build the filter/criteria UI (mobile-first)
- [ ] Build the results list with property cards
- [ ] Build the property detail view
- [ ] Client-side filtering and sorting
- [ ] Persist filter preferences in localStorage
- [ ] Show "last updated" timestamp from meta.json
- [ ] Deploy to GitHub Pages
- [ ] Verify the full pipeline: Actions scrape → commit → deploy → live site

**Definition of done:** A public URL where you can filter tri-state listings by
price, beds, baths, sqft, type, and sort by price/value/newest.

### Phase 2: Enrichment & Second Source

**Goal:** Better data, more coverage.

- [ ] Add Walk Score enrichment to the scraper pipeline
- [ ] Add Realtor.com adapter (RapidAPI, 100 req/month for validation)
- [ ] Add keyword search in descriptions
- [ ] Add map view (Leaflet or Mapbox GL JS, free tier)
- [ ] Add "new today" / "price reduced" badges based on daily diffs
- [ ] Add per-county data splitting if JSON size becomes an issue
- [ ] Consider StreetEasy scraper for NYC co-op/condo enrichment

### Phase 3: Advanced Features

**Goal:** Comprehensive coverage, power-user features.

- [ ] Saved searches with criteria presets
- [ ] Price history tracking (diff across daily snapshots in git)
- [ ] Zillow data enrichment (Zestimates, tax records) via Zillapi/APIllow
- [ ] Douglas Elliman "Black Label" scraper
- [ ] Rental listings (toggle buy/rent mode)
- [ ] Email/push alerts for new matches (would need a simple backend — 
      could use GitHub Actions + email API like SendGrid free tier)

---

## 12. Open Decisions

These are questions for Yash to answer during the build. Claude Code should ask
about these when they become relevant, not all at once upfront.

1. **Repo name:** `homefinder`, `home-finder`, `tristate-homes`, or something else?
2. **Custom domain:** Want to set one up, or is `username.github.io/repo` fine for now?
3. **Walk Score API key:** Yash needs to sign up at walkscore.com/professional/api.php
   and add the key as a GitHub Actions secret. This blocks Walk Score enrichment.
4. **Scrape time:** 6 AM ET daily is the default. Prefer a different time?
5. **Data retention:** Should git history preserve old listing snapshots (useful for
   price history) or should we squash data commits to keep repo size small?
6. **County scope:** Start with all 20 counties, or a smaller subset first for faster
   iteration? Manhattan + Brooklyn + a few NJ counties might be a good starting set.

---

## 13. Progress Tracker

Update this section as work progresses. Check off items from Phase 1 as they're
completed. Note any blockers, decisions made, or deviations from the plan.

```
[ ] Repo created
[ ] Project scaffolded (Vite + React + TS + Tailwind)
[ ] Python scraper adapted for JSON output
[ ] GitHub Actions workflow created
[ ] First successful automated scrape
[ ] Data verified (listings.json has real data)
[ ] Frontend: filter UI built
[ ] Frontend: results list built
[ ] Frontend: detail view built
[ ] Frontend: sorting working
[ ] Frontend: localStorage persistence
[ ] Deployed to GitHub Pages
[ ] Full pipeline verified end-to-end
```

**Blockers:**
- (none yet)

**Decisions made:**
- (record here as they're made)

**Deviations from plan:**
- (record here if anything changes)

---

## Appendix A: Redfin Response Shape Reference

### Autocomplete Response
```json
{
  "payload": {
    "sections": [
      {
        "rows": [
          {
            "id": "1713",
            "type": "5",
            "name": "Kings County, NY",
            "subName": "New York, USA"
          }
        ]
      }
    ]
  }
}
```

### GIS JSON Response (single home)
```json
{
  "homeData": {
    "propertyId": 12345,
    "propertyType": 2,
    "url": "/NY/Brooklyn/123-Main-St-11201/home/12345",
    "addressInfo": {
      "formattedStreetLine": "123 Main St",
      "city": "Brooklyn",
      "state": "NY",
      "zip": "11201",
      "centroid": {
        "centroid": { "latitude": 40.689, "longitude": -73.984 }
      }
    },
    "priceInfo": { "amount": 500000 },
    "bedInfo": { "value": 2 },
    "bathInfo": { "value": 1.5 },
    "sqftInfo": { "value": 1000 },
    "lotSize": { "value": 0 },
    "yearBuilt": { "yearBuilt": 1990 },
    "daysOnMarket": { "daysOnMarket": 15 },
    "hoaDuesInfo": { "amount": 300 },
    "mlsId": { "value": "ML12345" },
    "listingMetadata": { "mlsStatusText": "Active" }
  }
}
```

---

*Document version: 1.0 — August 2026*
*Authored in Claude.ai, intended for Claude Code execution.*
