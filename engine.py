"""Core search engine that orchestrates adapters, storage, and filtering."""

from __future__ import annotations

import logging
from typing import Optional

from home_finder.adapters.base import BaseAdapter
from home_finder.adapters.redfin import RedfinAdapter
from home_finder.config import TRI_STATE_COUNTIES
from home_finder.filters import apply_filters, sort_by_price
from home_finder.models import Property, SearchCriteria
from home_finder.storage import ChangeReport, ListingStore

logger = logging.getLogger(__name__)


class HomeFinder:
    """High-level search engine.

    Usage::

        finder = HomeFinder()
        results = finder.search_location("Brooklyn, NY", criteria)
        finder.close()
    """

    def __init__(
        self,
        adapters: Optional[list[BaseAdapter]] = None,
        db_path: Optional[str] = None,
    ):
        self._adapters = adapters or [RedfinAdapter()]
        self._store = ListingStore(db_path=db_path)

    def close(self) -> None:
        self._store.close()

    # ── Single-Location Search ───────────────────────────────────────

    def search_location(
        self,
        location: str,
        criteria: Optional[SearchCriteria] = None,
    ) -> list[Property]:
        """Search a single location across all adapters.

        Resolves *location* via each adapter's autocomplete, fetches
        listings with pagination, applies post-filters, and returns
        a deduplicated, sorted result set.
        """
        all_props: list[Property] = []

        for adapter in self._adapters:
            regions = adapter.resolve_location(location)
            if not regions:
                logger.warning(
                    "%s: could not resolve %r", adapter.source_name, location
                )
                continue

            # Use the first (best) match
            region = regions[0]
            logger.info(
                "%s: resolved %r -> %s (id=%d, type=%d)",
                adapter.source_name,
                location,
                region["name"],
                region["region_id"],
                region["region_type"],
            )

            props = adapter.search(
                region_id=region["region_id"],
                region_type=region["region_type"],
                criteria=criteria,
            )
            all_props.extend(props)

        # Deduplicate across sources
        all_props = self._deduplicate(all_props)

        # Apply post-fetch filters
        if criteria:
            all_props = apply_filters(all_props, criteria)

        return sort_by_price(all_props)

    # ── Region-Based Search (for sweeps) ─────────────────────────────

    def search_region(
        self,
        region_id: int,
        region_type: int,
        criteria: Optional[SearchCriteria] = None,
        adapter: Optional[BaseAdapter] = None,
    ) -> list[Property]:
        """Search a known region_id directly (skips autocomplete)."""
        adpt = adapter or self._adapters[0]
        props = adpt.search(region_id, region_type, criteria)
        if criteria:
            props = apply_filters(props, criteria)
        return sort_by_price(props)

    # ── Tri-State Full Sweep ─────────────────────────────────────────

    def sweep_tri_state(
        self,
        criteria: Optional[SearchCriteria] = None,
        counties: Optional[dict] = None,
    ) -> ChangeReport:
        """Run a full sweep of all tri-state counties.

        Fetches from the primary adapter, upserts into storage,
        and returns a ChangeReport with new/removed/changed listings.
        """
        regions = counties or TRI_STATE_COUNTIES
        adapter = self._adapters[0]
        all_props: list[Property] = []

        for name, info in regions.items():
            logger.info("Sweeping %s ...", name)
            props = adapter.search(
                region_id=info["region_id"],
                region_type=info["region_type"],
                criteria=criteria,
            )
            all_props.extend(props)
            logger.info("  -> %d listings", len(props))

        all_props = self._deduplicate(all_props)
        logger.info("Total after dedup: %d listings", len(all_props))

        # Detect changes against stored state
        report = self._store.detect_changes(adapter.source_name, all_props)

        # Persist the new snapshot
        self._store.upsert_batch(all_props)

        logger.info("Change report: %s", report.summary())
        return report

    # ── Storage Queries ──────────────────────────────────────────────

    def get_stored_listings(
        self,
        source: Optional[str] = None,
        zip_code: Optional[str] = None,
    ) -> list[dict]:
        """Retrieve stored active listings from the database."""
        return self._store.get_active(source=source, zip_code=zip_code)

    def count_stored(self, source: Optional[str] = None) -> int:
        return self._store.count_active(source=source)

    # ── Deduplication ────────────────────────────────────────────────

    @staticmethod
    def _deduplicate(properties: list[Property]) -> list[Property]:
        """Remove duplicates, keeping the record with the most data."""
        seen: dict[str, Property] = {}
        for prop in properties:
            fp = prop.fingerprint
            if fp not in seen:
                seen[fp] = prop
            else:
                existing = seen[fp]
                # Prefer the record with more non-None fields
                new_count = sum(
                    1 for v in prop.to_dict().values() if v is not None
                )
                old_count = sum(
                    1 for v in existing.to_dict().values() if v is not None
                )
                if new_count > old_count:
                    seen[fp] = prop
        return list(seen.values())
