#!/usr/bin/env python3
"""HomeFinder — Single-file tri-state property search.

Fetches real listings from Redfin's Stingray API, filters by your
criteria, and generates a self-contained HTML report you open in
your phone's browser.

Setup (Pydroid 3 on Android — recommended):
    1. Install "Pydroid 3" from Google Play Store
    2. Install "Pydroid Permissions Plugin" from Play Store
    3. Open Pydroid 3 → Menu → Pip → install "requests"
    4. Open this file in Pydroid 3 and tap Run

Setup (Termux on Android):
    pkg install python
    pip install requests
    python homefinder.py

Setup (Desktop):
    pip install requests
    python homefinder.py
"""

import argparse
import csv
import io
import json
import os
import platform
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

try:
    import requests
except ImportError:
    print("Missing dependency. Run: pip install requests")
    sys.exit(1)

# ── Configuration ────────────────────────────────────────────────────

REDFIN_BASE = "https://www.redfin.com"
REDFIN_GIS = f"{REDFIN_BASE}/stingray/api/gis"
REDFIN_AUTOCOMPLETE = f"{REDFIN_BASE}/stingray/do/location-autocomplete"
PAGE_SIZE = 350
REQUEST_DELAY = 2.0
JSON_PREFIX = "{}&&"

USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Mobile Safari/537.36"
)

def _detect_output_dir() -> str:
    """Pick a directory the user can easily find.

    On Android (Pydroid 3 / Termux), save to the shared Downloads
    folder so the report shows up in the system file manager.
    Everywhere else, use ~/homefinder_results.
    """
    android_download = "/storage/emulated/0/Download/HomeFinder"
    if os.path.isdir("/storage/emulated/0/Download"):
        return android_download
    return os.path.expanduser("~/homefinder_results")

OUTPUT_DIR = _detect_output_dir()

# ── Data Models ──────────────────────────────────────────────────────


@dataclass
class Property:
    address: str
    city: str
    state: str
    zip_code: str
    price: Optional[int] = None
    beds: Optional[int] = None
    baths: Optional[float] = None
    sqft: Optional[int] = None
    property_type: str = "other"
    status: str = "active"
    year_built: Optional[int] = None
    hoa_monthly: Optional[int] = None
    days_on_market: Optional[int] = None
    lot_sqft: Optional[int] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    url: str = ""
    source_id: str = ""

    @property
    def price_per_sqft(self) -> Optional[int]:
        if self.price and self.sqft and self.sqft > 0:
            return round(self.price / self.sqft)
        return None


@dataclass
class SearchCriteria:
    location: str = ""
    min_price: Optional[int] = None
    max_price: Optional[int] = None
    min_beds: Optional[int] = None
    max_beds: Optional[int] = None
    min_baths: Optional[float] = None
    min_sqft: Optional[int] = None
    max_sqft: Optional[int] = None
    property_types: list = field(default_factory=list)
    min_year_built: Optional[int] = None
    max_hoa: Optional[int] = None


# ── Redfin API Client ────────────────────────────────────────────────


class RedfinClient:
    """Thin client for Redfin's Stingray API."""

    PROP_TYPE_CODES = {
        "house": 1, "condo": 2, "townhouse": 3,
        "multifamily": 4, "land": 5, "other": 6,
    }

    STATUS_MAP = {
        "active": "active", "coming soon": "coming_soon",
        "pending": "pending", "contingent": "contingent",
        "sold": "sold", "closed": "sold",
    }

    TYPE_MAP = {
        1: "house", 2: "condo", 3: "townhouse",
        4: "multifamily", 5: "land", 6: "other",
    }

    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        })

    def resolve_location(self, query: str) -> Optional[dict]:
        """Autocomplete a location string to a region_id + region_type."""
        print(f"  Resolving location: {query}")
        try:
            resp = self._get(REDFIN_AUTOCOMPLETE, params={"location": query, "v": 2})
            raw = self._strip(resp.text)
            data = json.loads(raw)
        except Exception as exc:
            print(f"  ✗ Autocomplete failed: {exc}")
            return None

        for section in data.get("payload", {}).get("sections", []):
            for row in section.get("rows", []):
                rid = row.get("id")
                rtype = row.get("type")
                if rid is not None and rtype is not None:
                    name = row.get("name", query)
                    print(f"  ✓ Resolved to: {name} (id={rid}, type={rtype})")
                    return {"region_id": int(rid), "region_type": int(rtype), "name": name}

        print("  ✗ No results found")
        return None

    def search(self, region_id: int, region_type: int, criteria: SearchCriteria) -> list[Property]:
        """Fetch all listings with pagination."""
        all_props: list[Property] = []
        page = 1
        start = 0

        while True:
            params = self._build_params(region_id, region_type, criteria, page, start)
            print(f"  Fetching page {page} (offset {start})...")

            try:
                resp = self._get(REDFIN_GIS, params=params)
                resp.raise_for_status()
                raw = self._strip(resp.text)
                data = json.loads(raw)
            except Exception as exc:
                print(f"  ✗ Page {page} failed: {exc}")
                break

            payload = data.get("payload", {})
            homes = payload.get("homes", [])

            if not homes:
                break

            for home in homes:
                prop = self._parse_home(home)
                if prop is not None:
                    all_props.append(prop)

            total = payload.get("totalResultCount", 0)
            fetched = start + len(homes)
            print(f"    Got {len(homes)} listings ({fetched}/{total})")

            if fetched >= total:
                break

            page += 1
            start = fetched

        return all_props

    def _get(self, url: str, **kwargs) -> requests.Response:
        time.sleep(REQUEST_DELAY)
        return self._session.get(url, timeout=30, **kwargs)

    @staticmethod
    def _strip(text: str) -> str:
        return text[len(JSON_PREFIX):] if text.startswith(JSON_PREFIX) else text

    def _build_params(self, region_id, region_type, criteria, page=1, start=0):
        params = {
            "al": 1, "region_id": region_id, "region_type": region_type,
            "num_homes": PAGE_SIZE, "page_number": page, "start": start,
            "sf": "1,2,3,5,6,7", "status": 1, "uipt": "1,2,3,4,5,6,7,8", "v": 8,
        }
        if criteria.min_price is not None:
            params["min_price"] = criteria.min_price
        if criteria.max_price is not None:
            params["max_price"] = criteria.max_price
        if criteria.min_beds is not None:
            params["min_num_beds"] = criteria.min_beds
        if criteria.max_beds is not None:
            params["max_num_beds"] = criteria.max_beds
        if criteria.min_baths is not None:
            params["min_num_baths"] = int(criteria.min_baths)
        if criteria.min_sqft is not None:
            params["min_listing_approx_size"] = criteria.min_sqft
        if criteria.max_sqft is not None:
            params["max_listing_approx_size"] = criteria.max_sqft
        if criteria.min_year_built is not None:
            params["min_year_built"] = criteria.min_year_built
        if criteria.max_hoa is not None:
            params["hoa"] = criteria.max_hoa
        if criteria.property_types:
            codes = [str(self.PROP_TYPE_CODES[t]) for t in criteria.property_types if t in self.PROP_TYPE_CODES]
            if codes:
                params["uipt"] = ",".join(codes)
        return params

    def _parse_home(self, home: dict) -> Optional[Property]:
        hd = home.get("homeData", {})
        if not hd:
            return None

        addr = hd.get("addressInfo", {})
        address = addr.get("formattedStreetLine", "")
        zip_code = addr.get("zip", "")
        if not address or not zip_code:
            return None

        centroid = addr.get("centroid", {}).get("centroid", {})
        url_path = hd.get("url", "")
        status_raw = (hd.get("listingMetadata", {}).get("mlsStatusText") or "active").lower()
        status = "active"
        for key, val in self.STATUS_MAP.items():
            if key in status_raw:
                status = val
                break

        prop_type_code = self._safe_int(hd.get("propertyType"))
        prop_type = self.TYPE_MAP.get(prop_type_code, "other")

        return Property(
            address=address,
            city=addr.get("city", ""),
            state=addr.get("state", ""),
            zip_code=zip_code,
            price=self._safe_int(hd.get("priceInfo", {}).get("amount")),
            beds=self._safe_int(hd.get("bedInfo", {}).get("value")),
            baths=self._safe_float(hd.get("bathInfo", {}).get("value")),
            sqft=self._safe_int(hd.get("sqftInfo", {}).get("value")),
            property_type=prop_type,
            status=status,
            year_built=self._safe_int(hd.get("yearBuilt", {}).get("yearBuilt")),
            hoa_monthly=self._safe_int(hd.get("hoaDuesInfo", {}).get("amount")),
            days_on_market=self._safe_int(hd.get("daysOnMarket", {}).get("daysOnMarket")),
            lot_sqft=self._safe_int(hd.get("lotSize", {}).get("value")),
            latitude=self._safe_float(centroid.get("latitude")),
            longitude=self._safe_float(centroid.get("longitude")),
            url=f"{REDFIN_BASE}{url_path}" if url_path else "",
            source_id=str(hd.get("propertyId", "")),
        )

    @staticmethod
    def _safe_int(val) -> Optional[int]:
        if val is None or val == "":
            return None
        try:
            return int(float(val))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _safe_float(val) -> Optional[float]:
        if val is None or val == "":
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None


# ── Filtering ────────────────────────────────────────────────────────


def apply_filters(props: list[Property], criteria: SearchCriteria) -> list[Property]:
    """Post-filter for anything the API didn't handle server-side."""
    results = []
    for p in props:
        if criteria.min_price and p.price is not None and p.price < criteria.min_price:
            continue
        if criteria.max_price and p.price is not None and p.price > criteria.max_price:
            continue
        if criteria.min_beds and p.beds is not None and p.beds < criteria.min_beds:
            continue
        if criteria.max_beds and p.beds is not None and p.beds > criteria.max_beds:
            continue
        if criteria.min_baths and p.baths is not None and p.baths < criteria.min_baths:
            continue
        if criteria.min_sqft and p.sqft is not None and p.sqft < criteria.min_sqft:
            continue
        if criteria.max_sqft and p.sqft is not None and p.sqft > criteria.max_sqft:
            continue
        if criteria.min_year_built and p.year_built is not None and p.year_built < criteria.min_year_built:
            continue
        if criteria.max_hoa is not None and p.hoa_monthly is not None and p.hoa_monthly > criteria.max_hoa:
            continue
        if criteria.property_types and p.property_type not in criteria.property_types:
            continue
        results.append(p)
    results.sort(key=lambda p: (p.price is None, p.price or 0))
    return results


# ── HTML Report Generator ────────────────────────────────────────────


def generate_html(properties: list[Property], criteria: SearchCriteria, location_name: str) -> str:
    """Build a self-contained, mobile-optimized HTML report."""

    def fmt_price(p):
        return f"${p:,.0f}" if p else "—"

    def fmt_ppsf(price, sqft):
        return f"${round(price/sqft)}/ft²" if price and sqft and sqft > 0 else ""

    def score_color(v):
        if v is None: return "#666"
        if v >= 90: return "#22c55e"
        if v >= 70: return "#f59e0b"
        return "#f97316"

    def status_color(s):
        return {"active":"#22c55e","coming_soon":"#f59e0b","pending":"#f97316","sold":"#ef4444"}.get(s, "#666")

    def status_label(s):
        return {"active":"Active","coming_soon":"Coming Soon","pending":"Pending","sold":"Sold"}.get(s, s)

    def type_label(t):
        return {"house":"House","condo":"Condo","townhouse":"Townhouse","coop":"Co-op","multifamily":"Multi","land":"Land"}.get(t, t.title())

    now = datetime.now().strftime("%b %d, %Y at %I:%M %p")

    # Build criteria summary
    filters = []
    if criteria.min_price or criteria.max_price:
        lo = fmt_price(criteria.min_price) if criteria.min_price else "$0"
        hi = fmt_price(criteria.max_price) if criteria.max_price else "Any"
        filters.append(f"Price: {lo} – {hi}")
    if criteria.min_beds:
        filters.append(f"Beds: {criteria.min_beds}+")
    if criteria.min_baths:
        filters.append(f"Baths: {criteria.min_baths}+")
    if criteria.min_sqft:
        filters.append(f"Sqft: {criteria.min_sqft}+")
    if criteria.property_types:
        filters.append(f"Types: {', '.join(type_label(t) for t in criteria.property_types)}")
    filter_html = " · ".join(filters) if filters else "No filters applied"

    # Build property cards
    cards_html = ""
    for i, p in enumerate(properties):
        dom_class = "dom-new" if p.days_on_market is not None and p.days_on_market <= 7 else ""
        cards_html += f"""
        <a class="card" href="{p.url}" target="_blank" rel="noopener">
          <div class="card-top">
            <div class="card-left">
              <div class="card-meta">
                <span class="status-dot" style="background:{status_color(p.status)}"></span>
                <span>{type_label(p.property_type)} · {p.city}, {p.state}</span>
              </div>
              <div class="card-address">{p.address}</div>
            </div>
            <div class="card-right">
              <div class="card-price">{fmt_price(p.price)}</div>
              <div class="card-ppsf">{fmt_ppsf(p.price, p.sqft)}</div>
            </div>
          </div>
          <div class="card-stats">
            <span>{p.beds or '—'}bd</span>
            <span>{p.baths or '—'}ba</span>
            <span>{f'{p.sqft:,}' if p.sqft else '—'}ft²</span>
            {f'<span>HOA ${p.hoa_monthly}</span>' if p.hoa_monthly else ''}
            {f'<span>Built {p.year_built}</span>' if p.year_built else ''}
            <span class="dom {dom_class}" style="margin-left:auto">{f'{p.days_on_market}d' if p.days_on_market is not None else ''}</span>
          </div>
          <div class="card-badges">
            <span class="badge" style="background:{status_color(p.status)}22;color:{status_color(p.status)}">{status_label(p.status)}</span>
            {f'<span class="badge">🏠 {p.lot_sqft:,} lot</span>' if p.lot_sqft and p.lot_sqft > 0 else ''}
          </div>
        </a>"""

    if not properties:
        cards_html = """
        <div class="empty">
          <div class="empty-icon">🏠</div>
          <p>No properties matched your criteria.</p>
          <p class="hint">Try broadening your filters.</p>
        </div>"""

    # Price range summary
    if properties:
        prices = [p.price for p in properties if p.price]
        price_range = f"{fmt_price(min(prices))} – {fmt_price(max(prices))}" if prices else ""
    else:
        price_range = ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>HomeFinder — {location_name}</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background:#0a0f1a; color:#f1f5f9; font-family:system-ui,-apple-system,sans-serif; -webkit-font-smoothing:antialiased; }}
  .header {{ padding:16px; border-bottom:1px solid #1e293b; }}
  .header h1 {{ font-size:20px; font-weight:700; }}
  .header .sub {{ font-size:13px; color:#94a3b8; margin-top:4px; }}
  .header .range {{ font-size:11px; color:#64748b; background:#0f172a; padding:4px 10px; border-radius:6px; display:inline-block; margin-top:8px; }}
  .filters {{ padding:8px 16px; font-size:12px; color:#64748b; border-bottom:1px solid #1e293b; }}
  .list {{ padding:8px 12px 24px; }}
  .card {{ display:block; background:#141c2e; border:1px solid #1e293b; border-radius:12px; padding:14px; margin-bottom:10px; text-decoration:none; color:inherit; }}
  .card:active {{ background:#1a2540; }}
  .card-top {{ display:flex; justify-content:space-between; align-items:flex-start; }}
  .card-left {{ flex:1; min-width:0; }}
  .card-right {{ text-align:right; flex-shrink:0; margin-left:12px; }}
  .card-meta {{ display:flex; align-items:center; gap:6px; font-size:12px; color:#94a3b8; margin-bottom:4px; }}
  .status-dot {{ width:7px; height:7px; border-radius:50%; flex-shrink:0; }}
  .card-address {{ font-size:14px; font-weight:500; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
  .card-price {{ font-size:16px; font-weight:700; }}
  .card-ppsf {{ font-size:11px; color:#94a3b8; }}
  .card-stats {{ display:flex; gap:12px; margin-top:10px; font-size:13px; color:#94a3b8; flex-wrap:wrap; }}
  .dom {{ font-size:11px; }}
  .dom-new {{ color:#22c55e; font-weight:600; }}
  .card-badges {{ display:flex; gap:6px; margin-top:8px; flex-wrap:wrap; }}
  .badge {{ font-size:11px; padding:2px 8px; border-radius:4px; background:rgba(255,255,255,0.06); color:#94a3b8; }}
  .empty {{ padding:60px 32px; text-align:center; }}
  .empty-icon {{ font-size:48px; margin-bottom:12px; }}
  .empty p {{ font-size:15px; color:#94a3b8; }}
  .hint {{ font-size:13px; color:#64748b; margin-top:4px; }}
  .footer {{ padding:16px; text-align:center; font-size:11px; color:#475569; border-top:1px solid #1e293b; }}
</style>
</head>
<body>
  <div class="header">
    <h1>HomeFinder</h1>
    <div class="sub">{len(properties)} {'property' if len(properties)==1 else 'properties'} in {location_name}</div>
    {f'<div class="range">{price_range}</div>' if price_range else ''}
  </div>
  <div class="filters">{filter_html}</div>
  <div class="list">{cards_html}</div>
  <div class="footer">Generated {now} · Data from Redfin</div>
</body>
</html>"""


# ── Interactive Input ────────────────────────────────────────────────


def ask(prompt, default=None, cast=None):
    """Prompt with optional default and type casting."""
    suffix = f" [{default}]" if default is not None else ""
    val = input(f"  {prompt}{suffix}: ").strip()
    if not val:
        return default
    if cast:
        try:
            return cast(val)
        except (ValueError, TypeError):
            return default
    return val


def interactive_criteria() -> SearchCriteria:
    """Walk the user through setting search criteria."""
    print("\n╔══════════════════════════════════════╗")
    print("║         HomeFinder Search            ║")
    print("╚══════════════════════════════════════╝\n")

    location = ask("Location (city, ZIP, or neighborhood)", "Brooklyn, NY")

    print("\n── Price ──")
    min_price = ask("Min price", None, int)
    max_price = ask("Max price", None, int)

    print("\n── Layout ──")
    min_beds = ask("Min bedrooms", None, int)
    max_beds = ask("Max bedrooms", None, int)
    min_baths = ask("Min bathrooms", None, float)
    min_sqft = ask("Min sqft", None, int)
    max_sqft = ask("Max sqft", None, int)

    print("\n── Property Types ──")
    print("  Options: house, condo, townhouse, multifamily, land")
    types_raw = ask("Types (comma-separated, or blank for all)", "")
    property_types = [t.strip().lower() for t in types_raw.split(",") if t.strip()] if types_raw else []

    print("\n── More Filters ──")
    min_year = ask("Built after year", None, int)
    max_hoa = ask("Max monthly HOA", None, int)

    return SearchCriteria(
        location=location,
        min_price=min_price,
        max_price=max_price,
        min_beds=min_beds,
        max_beds=max_beds,
        min_baths=min_baths,
        min_sqft=min_sqft,
        max_sqft=max_sqft,
        property_types=property_types,
        min_year_built=min_year,
        max_hoa=max_hoa,
    )


# ── CLI Argument Parsing ─────────────────────────────────────────────


def parse_args():
    parser = argparse.ArgumentParser(
        description="HomeFinder — Tri-state property search",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
               "  python homefinder.py\n"
               "  python homefinder.py --location 'Hoboken, NJ' --max-price 700000 --min-beds 2\n"
               "  python homefinder.py -l '11201' --types condo coop --max-hoa 800\n",
    )
    parser.add_argument("-l", "--location", help="City, ZIP, or neighborhood")
    parser.add_argument("--min-price", type=int)
    parser.add_argument("--max-price", type=int)
    parser.add_argument("--min-beds", type=int)
    parser.add_argument("--max-beds", type=int)
    parser.add_argument("--min-baths", type=float)
    parser.add_argument("--min-sqft", type=int)
    parser.add_argument("--max-sqft", type=int)
    parser.add_argument("--types", nargs="+", help="e.g. house condo townhouse")
    parser.add_argument("--min-year", type=int, help="Built after year")
    parser.add_argument("--max-hoa", type=int, help="Max monthly HOA")
    parser.add_argument("--no-open", action="store_true", help="Don't auto-open the report")
    return parser.parse_args()


# ── Main ─────────────────────────────────────────────────────────────


def main():
    args = parse_args()

    # Use CLI args if provided, otherwise go interactive
    if args.location:
        criteria = SearchCriteria(
            location=args.location,
            min_price=args.min_price,
            max_price=args.max_price,
            min_beds=args.min_beds,
            max_beds=args.max_beds,
            min_baths=args.min_baths,
            min_sqft=args.min_sqft,
            max_sqft=args.max_sqft,
            property_types=args.types or [],
            min_year_built=args.min_year,
            max_hoa=args.max_hoa,
        )
    else:
        criteria = interactive_criteria()

    print(f"\n🔍 Searching: {criteria.location}")
    print("─" * 40)

    client = RedfinClient()

    # Resolve location
    region = client.resolve_location(criteria.location)
    if not region:
        print("\n✗ Could not resolve that location. Try a city name or ZIP code.")
        sys.exit(1)

    # Fetch listings
    print(f"\n📡 Fetching listings from Redfin...")
    properties = client.search(region["region_id"], region["region_type"], criteria)
    print(f"  Fetched {len(properties)} raw listings")

    # Apply post-filters
    filtered = apply_filters(properties, criteria)
    print(f"  After filtering: {len(filtered)} matches")

    if filtered:
        prices = [p.price for p in filtered if p.price]
        if prices:
            print(f"  Price range: ${min(prices):,.0f} – ${max(prices):,.0f}")

    # Generate report
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_loc = criteria.location.replace(",", "").replace(" ", "_").lower()
    filename = f"homefinder_{safe_loc}_{timestamp}.html"
    filepath = os.path.join(OUTPUT_DIR, filename)

    html = generate_html(filtered, criteria, region["name"])
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)

    abs_path = os.path.abspath(filepath)
    print(f"\n✓ Report saved: {abs_path}")

    # Try to open in browser (platform-aware)
    if not args.no_open:
        opened = _open_report(abs_path)
        if not opened:
            print("  Open the file above in your browser to view results")

    print()


def _open_report(filepath: str) -> bool:
    """Open the HTML report in the system browser.

    On Android, Python's webbrowser module is unavailable, so we
    use an 'am start' intent to hand the file to Chrome / the
    default browser.  On desktop, fall back to webbrowser.open().
    """
    file_uri = f"file://{filepath}"

    # Android (Pydroid 3 or Termux)
    if os.path.isdir("/storage/emulated/0"):
        try:
            subprocess.run(
                [
                    "am", "start", "--user", "0",
                    "-a", "android.intent.action.VIEW",
                    "-d", file_uri,
                    "-t", "text/html",
                ],
                capture_output=True,
                timeout=5,
            )
            print("  Opened in browser")
            return True
        except Exception:
            # am not available (rare) — fall through
            pass

    # Desktop / other
    try:
        import webbrowser
        webbrowser.open(file_uri)
        print("  Opened in browser")
        return True
    except Exception:
        return False


if __name__ == "__main__":
    main()
