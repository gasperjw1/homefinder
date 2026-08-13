#!/usr/bin/env python3
"""
HomeFinder — tri-state county sweep.

Fetches all active listings from Redfin's Stingray API across 19 tri-state
counties, deduplicates by address fingerprint, and writes:
  public/data/listings.json — full listing dataset for the frontend
  public/data/meta.json     — scrape metadata (counts, errors, duration)

Usage:
    python scraper/run_sweep.py [--counties manhattan brooklyn]
    python scraper/run_sweep.py  (default: all 19 counties)
"""

import argparse
import hashlib
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Optional

try:
    import requests
except ImportError:
    print("Missing dependency: pip install requests")
    sys.exit(1)

# ── Constants ─────────────────────────────────────────────────────────

REDFIN_BASE = "https://www.redfin.com"
REDFIN_GIS = f"{REDFIN_BASE}/stingray/api/gis"
REDFIN_AUTOCOMPLETE = f"{REDFIN_BASE}/stingray/do/location-autocomplete"
PAGE_SIZE = 350
REQUEST_DELAY = 2.0
JSON_PREFIX = "{}&&"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(REPO_ROOT, "public", "data")
LISTINGS_PATH = os.path.join(OUTPUT_DIR, "listings.json")
META_PATH = os.path.join(OUTPUT_DIR, "meta.json")

# Valid tri-state states — safety filter to block out-of-region results
# if a region ID ever resolves to the wrong area.
TRI_STATE_STATES = {"NY", "NJ", "CT"}

# County search terms and fallback region IDs.
# Region IDs are resolved fresh via autocomplete at scrape time;
# these fallbacks are only used if autocomplete fails.
TRI_STATE_COUNTIES = {
    "manhattan":     {"name": "New York County, NY",    "region_id": 1839, "region_type": 5},
    "brooklyn":      {"name": "Kings County, NY",       "region_id": 1713, "region_type": 5},
    "queens":        {"name": "Queens County, NY",      "region_id": 1900, "region_type": 5},
    "bronx":         {"name": "Bronx County, NY",       "region_id": 1587, "region_type": 5},
    "staten_island": {"name": "Richmond County, NY",    "region_id": 1906, "region_type": 5},
    "westchester":   {"name": "Westchester County, NY", "region_id": 2068, "region_type": 5},
    "nassau":        {"name": "Nassau County, NY",      "region_id": 1840, "region_type": 5},
    "suffolk":       {"name": "Suffolk County, NY",     "region_id": 1986, "region_type": 5},
    "rockland":      {"name": "Rockland County, NY",    "region_id": 1919, "region_type": 5},
    "bergen":        {"name": "Bergen County, NJ",      "region_id": 1561, "region_type": 5},
    "hudson":        {"name": "Hudson County, NJ",      "region_id": 1682, "region_type": 5},
    "essex":         {"name": "Essex County, NJ",       "region_id": 1625, "region_type": 5},
    "passaic":       {"name": "Passaic County, NJ",     "region_id": 1879, "region_type": 5},
    "union":         {"name": "Union County, NJ",       "region_id": 2038, "region_type": 5},
    "middlesex":     {"name": "Middlesex County, NJ",   "region_id": 1806, "region_type": 5},
    "morris":        {"name": "Morris County, NJ",      "region_id": 1833, "region_type": 5},
    "monmouth":      {"name": "Monmouth County, NJ",    "region_id": 1824, "region_type": 5},
    "fairfield":     {"name": "Fairfield County, CT",   "region_id": 1630, "region_type": 5},
    "new_haven":     {"name": "New Haven County, CT",   "region_id": 1847, "region_type": 5},
}

PROP_TYPE_MAP = {
    1: "house", 2: "condo", 3: "townhouse",
    4: "multifamily", 5: "land", 6: "other",
}

STATUS_KEYWORDS = {
    "coming soon": "coming_soon",
    "pending":     "pending",
    "contingent":  "contingent",
    "sold":        "sold",
    "closed":      "sold",
    "active":      "active",
}


# ── Data Model ────────────────────────────────────────────────────────

@dataclass
class Property:
    source: str
    source_id: str
    address: str
    city: str
    state: str
    zip_code: str
    price: Optional[int]
    beds: Optional[int]
    baths: Optional[float]
    sqft: Optional[int]
    property_type: str
    status: str
    year_built: Optional[int]
    hoa_monthly: Optional[int]
    days_on_market: Optional[int]
    lot_sqft: Optional[int]
    latitude: Optional[float]
    longitude: Optional[float]
    url: str
    mls_id: Optional[str]
    walk_score: Optional[int]
    transit_score: Optional[int]
    bike_score: Optional[int]
    description: Optional[str]
    scraped_at: str

    @property
    def fingerprint(self) -> str:
        raw = f"{self.address.lower().strip()}|{self.zip_code.strip()}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    @property
    def price_per_sqft(self) -> Optional[int]:
        if self.price and self.sqft and self.sqft > 0:
            return round(self.price / self.sqft)
        return None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["fingerprint"] = self.fingerprint
        d["price_per_sqft"] = self.price_per_sqft
        return d

    def non_null_count(self) -> int:
        return sum(1 for v in asdict(self).values() if v is not None)


# ── Redfin API Client ─────────────────────────────────────────────────

class RedfinClient:
    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
        })

    def resolve_region(self, county_name: str, fallback_id: int, fallback_type: int) -> dict:
        """Call autocomplete to get the current region_id for a county name.

        Falls back to the hard-coded ID if autocomplete fails or returns no
        county-level (type=5) result.
        """
        try:
            time.sleep(REQUEST_DELAY)
            resp = self._session.get(
                REDFIN_AUTOCOMPLETE,
                params={"location": county_name, "v": 2},
                timeout=30,
            )
            resp.raise_for_status()
            text = resp.text
            if text.startswith(JSON_PREFIX):
                text = text[len(JSON_PREFIX):]
            data = json.loads(text)

            for section in data.get("payload", {}).get("sections", []):
                for row in section.get("rows", []):
                    if row.get("type") == "5":  # county
                        resolved_id = int(row["id"])
                        if resolved_id != fallback_id:
                            print(f"    Region ID updated: {fallback_id} → {resolved_id}")
                        return {"region_id": resolved_id, "region_type": 5}
        except Exception as e:
            print(f"    Autocomplete failed ({county_name}): {e} — using fallback id={fallback_id}")

        return {"region_id": fallback_id, "region_type": fallback_type}

    def search_county(self, county_key: str, county_info: dict) -> list[Property]:
        display_name = county_info["name"]
        print(f"\n  [{county_key}] {display_name}")

        # Resolve the current region ID via autocomplete
        region = self.resolve_region(
            display_name,
            county_info["region_id"],
            county_info["region_type"],
        )
        region_id = region["region_id"]
        region_type = region["region_type"]

        all_props: list[Property] = []
        page = 1
        start = 0
        scraped_at = datetime.now(timezone.utc).isoformat()

        while True:
            params = {
                "al": 1,
                "region_id": region_id,
                "region_type": region_type,
                "num_homes": PAGE_SIZE,
                "page_number": page,
                "start": start,
                "sf": "1,2,3,5,6,7",
                "status": 1,
                "uipt": "1,2,3,4,5,6,7,8",
                "v": 8,
            }

            try:
                time.sleep(REQUEST_DELAY)
                resp = self._session.get(REDFIN_GIS, params=params, timeout=30)
                resp.raise_for_status()
                text = resp.text
                if text.startswith(JSON_PREFIX):
                    text = text[len(JSON_PREFIX):]
                data = json.loads(text)
            except requests.exceptions.HTTPError as e:
                print(f"    HTTP error on page {page}: {e}")
                break
            except Exception as e:
                print(f"    Error on page {page}: {e}")
                break

            payload = data.get("payload", {})
            homes = payload.get("homes", [])

            if not homes:
                break

            parsed = 0
            for home in homes:
                prop = _parse_home(home, scraped_at)
                if prop is not None:
                    all_props.append(prop)
                    parsed += 1

            skipped = len(homes) - parsed
            print(f"    Page {page}: {len(homes)} returned, {parsed} parsed"
                  + (f", {skipped} skipped (out-of-region)" if skipped else "")
                  + f" (total: {len(all_props)})")

            # Paginate until page is not full (totalResultCount removed from API)
            if len(homes) < PAGE_SIZE:
                break

            page += 1
            start += len(homes)

        print(f"    Done: {len(all_props)} listings")
        return all_props


def _parse_home(home: dict, scraped_at: str) -> Optional[Property]:
    """Parse a single home object from the flat Redfin GIS response (2026+ format)."""

    # Hard filter: only keep tri-state listings
    state = home.get("state", "")
    if state not in TRI_STATE_STATES:
        return None

    address = (home.get("streetLine") or {}).get("value", "").strip()
    zip_code = str((home.get("postalCode") or {}).get("value", "") or home.get("zip", "")).strip()

    if not address or not zip_code:
        return None

    lat_lon = (home.get("latLong") or {}).get("value", {})
    url_path = home.get("url", "")

    status_raw = (home.get("mlsStatus") or "active").lower()
    status = "active"
    for keyword, canonical in STATUS_KEYWORDS.items():
        if keyword in status_raw:
            status = canonical
            break

    prop_type_code = _safe_int(home.get("propertyType"))
    prop_type = PROP_TYPE_MAP.get(prop_type_code, "other")

    mls_raw = home.get("mlsId", {})
    mls_id = str(mls_raw.get("value", "")).strip() or None if isinstance(mls_raw, dict) else None

    hoa_raw = home.get("hoa", {})
    hoa = _safe_int(hoa_raw.get("value")) if isinstance(hoa_raw, dict) else None

    return Property(
        source="redfin",
        source_id=str(home.get("propertyId", "")),
        address=address,
        city=home.get("city", ""),
        state=state,
        zip_code=zip_code,
        price=_safe_int((home.get("price") or {}).get("value")),
        beds=_safe_int(home.get("beds")),
        baths=_safe_float(home.get("baths")),
        sqft=_safe_int((home.get("sqFt") or {}).get("value")),
        property_type=prop_type,
        status=status,
        year_built=_safe_int((home.get("yearBuilt") or {}).get("value")),
        hoa_monthly=hoa,
        days_on_market=_safe_int((home.get("dom") or {}).get("value")),
        lot_sqft=_safe_int((home.get("lotSize") or {}).get("value")),
        latitude=_safe_float(lat_lon.get("latitude")),
        longitude=_safe_float(lat_lon.get("longitude")),
        url=f"{REDFIN_BASE}{url_path}" if url_path else "",
        mls_id=mls_id,
        walk_score=None,
        transit_score=None,
        bike_score=None,
        description=home.get("listingRemarks"),
        scraped_at=scraped_at,
    )


def _safe_int(val) -> Optional[int]:
    if val is None or val == "":
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def _safe_float(val) -> Optional[float]:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


# ── Deduplication ─────────────────────────────────────────────────────

def deduplicate(properties: list[Property]) -> list[Property]:
    seen: dict[str, Property] = {}
    for prop in properties:
        fp = prop.fingerprint
        if fp not in seen or prop.non_null_count() > seen[fp].non_null_count():
            seen[fp] = prop
    return list(seen.values())


# ── Safety Check ──────────────────────────────────────────────────────

def load_previous_count() -> int:
    if not os.path.exists(LISTINGS_PATH):
        return 0
    try:
        with open(LISTINGS_PATH, "r") as f:
            data = json.load(f)
        return data.get("meta", {}).get("total_listings", 0)
    except Exception:
        return 0


# ── Output Writers ────────────────────────────────────────────────────

def write_listings(listings: list[Property], meta: dict) -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    payload = {
        "meta": {
            "last_updated": meta["last_updated"],
            "total_listings": len(listings),
            "source": "redfin",
        },
        "listings": [p.to_dict() for p in listings],
    }
    with open(LISTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, separators=(",", ":"))
    print(f"\n  Written: {LISTINGS_PATH} ({os.path.getsize(LISTINGS_PATH) / 1024:.1f} KB)")


def write_meta(meta: dict) -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    print(f"  Written: {META_PATH}")


# ── Main ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="HomeFinder county sweep")
    parser.add_argument(
        "--counties", nargs="+", metavar="KEY",
        choices=list(TRI_STATE_COUNTIES.keys()),
        help="Specific counties to sweep (default: all)",
    )
    args = parser.parse_args()

    counties = (
        {k: TRI_STATE_COUNTIES[k] for k in args.counties}
        if args.counties
        else TRI_STATE_COUNTIES
    )

    print("=" * 60)
    print(f"HomeFinder sweep — {len(counties)} counties")
    print("=" * 60)

    client = RedfinClient()
    start_time = time.monotonic()
    all_props: list[Property] = []
    by_county: dict[str, int] = {}
    errors: list[dict] = []

    for county_key, county_info in counties.items():
        try:
            props = client.search_county(county_key, county_info)
            by_county[county_info["name"]] = len(props)
            all_props.extend(props)
        except Exception as e:
            msg = f"{county_info['name']}: {e}"
            print(f"  ERROR: {msg}")
            errors.append({"county": county_info["name"], "error": str(e)})
            by_county[county_info["name"]] = 0

    print(f"\nTotal raw listings: {len(all_props)}")
    all_props = deduplicate(all_props)
    print(f"After dedup: {len(all_props)}")

    # Safety check: don't overwrite with a dramatically smaller dataset.
    # Disabled for the first real run (prev_count = 0 from bad data).
    prev_count = load_previous_count()
    if prev_count > 100 and len(all_props) < prev_count * 0.5:
        print(f"\nSAFETY: {len(all_props)} listings is <50% of previous {prev_count}. Aborting write.")
        sys.exit(1)

    duration = time.monotonic() - start_time
    last_updated = datetime.now(timezone.utc).isoformat()

    by_status: dict[str, int] = {}
    for p in all_props:
        by_status[p.status] = by_status.get(p.status, 0) + 1

    meta = {
        "last_updated": last_updated,
        "total_listings": len(all_props),
        "by_county": by_county,
        "by_status": by_status,
        "scrape_duration_seconds": round(duration, 1),
        "errors": errors,
    }

    write_listings(all_props, meta)
    write_meta(meta)

    print(f"\nDone in {duration:.1f}s")
    if errors:
        print(f"WARNING: {len(errors)} county error(s) — see meta.json")
        sys.exit(1 if len(errors) == len(counties) else 0)


if __name__ == "__main__":
    main()
