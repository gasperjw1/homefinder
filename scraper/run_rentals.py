#!/usr/bin/env python3
from __future__ import annotations
"""
HomeFinder — NYC borough rental sweep (Redfin rentals API).

Fetches rental listings from Redfin's rentals search API for the 5 NYC
boroughs and writes:
  public/data/rentals/{key}.json   — per-borough rental arrays
  public/data/rentals_meta.json    — scrape metadata for the sidebar

Usage:
    python scraper/run_rentals.py
    python scraper/run_rentals.py --boroughs brooklyn queens
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
REDFIN_RENTALS = f"{REDFIN_BASE}/stingray/api/v1/search/rentals"
PAGE_SIZE = 350
MIN_RENT = 500        # $/month floor — filters test entries
REQUEST_DELAY = 2.0

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(REPO_ROOT, "public", "data")
RENTALS_DIR = os.path.join(OUTPUT_DIR, "rentals")
META_PATH = os.path.join(OUTPUT_DIR, "rentals_meta.json")

# NYC boroughs — uses same county region IDs as the for-sale scraper
NYC_BOROUGHS = {
    "manhattan":     {"name": "New York County, NY",  "region_id": 1975, "region_type": 5, "market": "newyork"},
    "brooklyn":      {"name": "Kings County, NY",     "region_id": 1968, "region_type": 5, "market": "newyork"},
    "queens":        {"name": "Queens County, NY",    "region_id": 1985, "region_type": 5, "market": "newyork"},
    "bronx":         {"name": "Bronx County, NY",     "region_id": 1947, "region_type": 5, "market": "newyork"},
    "staten_island": {"name": "Richmond County, NY",  "region_id": 1987, "region_type": 5, "market": "newyork"},
}

RENTAL_PROP_TYPE_MAP = {
    1: "house",
    2: "condo",
    3: "townhouse",
    4: "multifamily",
    5: "multifamily",   # apartment buildings
    6: "other",
    7: "other",
    8: "other",
}


# ── Data Model ────────────────────────────────────────────────────────

@dataclass
class RentalProperty:
    source: str
    source_id: str
    listing_type: str
    address: str
    city: str
    state: str
    zip_code: str
    price: Optional[int]
    price_max: Optional[int]
    beds: Optional[int]
    beds_max: Optional[int]
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
    amenities: list
    num_available_units: Optional[int]
    property_name: Optional[str]
    scraped_at: str

    @property
    def fingerprint(self) -> str:
        raw = f"{self.address.lower().strip()}|{self.zip_code.strip()}|{self.listing_type}"
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


# ── Redfin Rentals API Client ─────────────────────────────────────────

class RedfinRentalsClient:
    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
        })

    def search_borough(self, borough_key: str, info: dict) -> list[RentalProperty]:
        display_name = info["name"]
        region_id = info["region_id"]
        region_type = info["region_type"]
        market = info["market"]
        print(f"\n  [{borough_key}] {display_name} (region_id={region_id})")

        all_props: list[RentalProperty] = []
        page = 1
        start = 0
        scraped_at = datetime.now(timezone.utc).isoformat()

        while True:
            params = {
                "al": 1,
                "consolidateBuildings": "true",
                "includeKeyFacts": "true",
                "includeMatchedUnitsCount": "true",
                "isRentals": "true",
                "market": market,
                "num_homes": PAGE_SIZE,
                "ord": "redfin-recommended-asc",
                "page_number": page,
                "region_id": region_id,
                "region_type": region_type,
                "sf": "1,2,3,5,6,7",
                "start": start,
                "status": 9,
                "uipt": "1,2,3,4",
                "use_max_pins": "true",
                "v": 8,
            }

            try:
                time.sleep(REQUEST_DELAY)
                resp = self._session.get(REDFIN_RENTALS, params=params, timeout=30)
                resp.raise_for_status()
                text = resp.text
                if text.startswith("{}&&"):
                    text = text[4:]
                data = json.loads(text)
            except requests.exceptions.HTTPError as e:
                print(f"    HTTP error on page {page}: {e}")
                break
            except Exception as e:
                print(f"    Error on page {page}: {e}")
                break

            payload = data.get("payload", data)
            homes = payload.get("homes", [])

            if not homes:
                break

            parsed = 0
            for home in homes:
                prop = _parse_rental(home, scraped_at)
                if prop is not None:
                    all_props.append(prop)
                    parsed += 1

            skipped = len(homes) - parsed
            print(f"    Page {page}: {len(homes)} returned, {parsed} parsed"
                  + (f", {skipped} skipped" if skipped else "")
                  + f" (total: {len(all_props)})")

            if len(homes) < PAGE_SIZE:
                break

            page += 1
            start += len(homes)

        print(f"    Done: {len(all_props)} listings")
        return all_props


def _parse_rental(home: dict, scraped_at: str) -> Optional[RentalProperty]:
    home_data = home.get("homeData", {})
    rental_ext = home.get("rentalExtension", {})

    addr_info = home_data.get("addressInfo", {})
    centroid = addr_info.get("centroid", {}).get("centroid", {})

    address = addr_info.get("formattedStreetLine", "").strip()
    city = addr_info.get("city", "").strip()
    state = addr_info.get("state", "").strip()
    zip_code = str(addr_info.get("zip", "") or "").strip()

    if not address or not zip_code:
        return None

    # Price: minimum rent across available units
    price_range = rental_ext.get("rentPriceRange", {}) or {}
    price = _safe_int(price_range.get("min"))
    price_max = _safe_int(price_range.get("max"))

    if price is not None and price < MIN_RENT:
        return None

    bed_range = rental_ext.get("bedRange", {}) or {}
    bath_range = rental_ext.get("bathRange", {}) or {}
    sqft_range = rental_ext.get("sqftRange", {}) or {}

    url_path = home_data.get("url", "")

    # Amenities from keyFacts (exclude unit-count facts)
    key_facts = rental_ext.get("keyFacts") or []
    amenities = []
    for kf in key_facts:
        desc = (kf.get("description") or "").strip()
        if desc and "unit" not in desc.lower():
            amenities.append(desc.upper())

    prop_type_code = _safe_int(home_data.get("propertyType"))
    prop_type = RENTAL_PROP_TYPE_MAP.get(prop_type_code, "other")

    return RentalProperty(
        source="redfin",
        source_id=str(rental_ext.get("rentalId", home_data.get("propertyId", ""))),
        listing_type="rent",
        address=address,
        city=city,
        state=state,
        zip_code=zip_code,
        price=price,
        price_max=price_max,
        beds=_safe_int(bed_range.get("min")),
        beds_max=_safe_int(bed_range.get("max")),
        baths=_safe_float(bath_range.get("min")),
        sqft=_safe_int(sqft_range.get("min")),
        property_type=prop_type,
        status="active",
        year_built=None,
        hoa_monthly=None,
        days_on_market=None,
        lot_sqft=None,
        latitude=_safe_float(centroid.get("latitude")),
        longitude=_safe_float(centroid.get("longitude")),
        url=f"{REDFIN_BASE}{url_path}" if url_path else "",
        mls_id=None,
        walk_score=None,
        transit_score=None,
        bike_score=None,
        description=rental_ext.get("description"),
        amenities=amenities,
        num_available_units=_safe_int(rental_ext.get("numAvailableUnits")),
        property_name=rental_ext.get("propertyName") or None,
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

def deduplicate(properties: list[RentalProperty]) -> list[RentalProperty]:
    seen: dict[str, RentalProperty] = {}
    for prop in properties:
        fp = prop.fingerprint
        if fp not in seen or prop.non_null_count() > seen[fp].non_null_count():
            seen[fp] = prop
    return list(seen.values())


# ── Output Writers ────────────────────────────────────────────────────

def write_borough_file(borough_key: str, listings: list[RentalProperty]) -> None:
    os.makedirs(RENTALS_DIR, exist_ok=True)
    path = os.path.join(RENTALS_DIR, f"{borough_key}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump([p.to_dict() for p in listings], f, separators=(",", ":"))
    print(f"    Written: {path} ({os.path.getsize(path) / 1024:.1f} KB, {len(listings)} listings)")


def write_meta(meta: dict) -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    print(f"  Written: {META_PATH}")


# ── Main ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="HomeFinder NYC rental sweep")
    parser.add_argument(
        "--boroughs", nargs="+", metavar="KEY",
        choices=list(NYC_BOROUGHS.keys()),
        help="Specific boroughs to sweep (default: all 5)",
    )
    args = parser.parse_args()

    boroughs = (
        {k: NYC_BOROUGHS[k] for k in args.boroughs}
        if args.boroughs
        else NYC_BOROUGHS
    )

    print("=" * 60)
    print(f"HomeFinder rental sweep — {len(boroughs)} borough(s)")
    print("=" * 60)

    client = RedfinRentalsClient()
    start_time = time.monotonic()
    all_props: list[RentalProperty] = []
    props_by_borough: dict[str, list[RentalProperty]] = {}
    errors: list[dict] = []

    for borough_key, borough_info in boroughs.items():
        try:
            props = client.search_borough(borough_key, borough_info)
            props_by_borough[borough_key] = props
            all_props.extend(props)
        except Exception as e:
            msg = f"{borough_info['name']}: {e}"
            print(f"  ERROR: {msg}")
            errors.append({"borough": borough_info["name"], "error": str(e)})
            props_by_borough[borough_key] = []

    print(f"\nTotal raw listings: {len(all_props)}")
    all_props = deduplicate(all_props)
    print(f"After dedup: {len(all_props)}")

    duration = time.monotonic() - start_time
    last_updated = datetime.now(timezone.utc).isoformat()

    # Structured borough metadata for the frontend sidebar
    boroughs_meta: dict[str, dict] = {}
    for borough_key, borough_info in NYC_BOROUGHS.items():
        state_code = borough_info["name"].rsplit(", ", 1)[-1]
        boroughs_meta[borough_key] = {
            "name": borough_info["name"],
            "state": state_code,
            "count": len(props_by_borough.get(borough_key, [])),
        }

    meta = {
        "last_updated": last_updated,
        "total_listings": len(all_props),
        "source": "redfin",
        "counties": boroughs_meta,
        "scrape_duration_seconds": round(duration, 1),
        "errors": errors,
    }

    write_meta(meta)

    print(f"\nWriting per-borough files...")
    for borough_key, props in props_by_borough.items():
        write_borough_file(borough_key, props)

    print(f"\nDone in {duration:.1f}s")
    if errors:
        print(f"WARNING: {len(errors)} borough error(s) — see rentals_meta.json")
        sys.exit(1 if len(errors) == len(boroughs) else 0)


if __name__ == "__main__":
    main()
