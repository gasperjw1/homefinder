import { useState, useEffect, useMemo } from 'react'
import { Virtuoso } from 'react-virtuoso'
import type { Property, ListingsMeta, SearchCriteria } from './types'
import { DEFAULT_FILTERS, COUNTY_GROUPS, applyFilters } from './types'

type ListingMode = 'buy' | 'rent'
import FilterPanel from './components/FilterPanel'
import PropertyCard from './components/PropertyCard'
import PropertyDetail from './components/PropertyDetail'
import StatsBar from './components/StatsBar'

const STORAGE_KEY = 'homefinder_filters'

function loadSavedFilters(): SearchCriteria {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) return { ...DEFAULT_FILTERS, ...JSON.parse(raw) }
  } catch {}
  return DEFAULT_FILTERS
}

export default function App() {
  const [meta, setMeta] = useState<ListingsMeta | null>(null)
  const [loadingMeta, setLoadingMeta] = useState(true)
  const [metaError, setMetaError] = useState<string | null>(null)

  const [listings, setListings] = useState<Property[]>([])
  const [loadingCounties, setLoadingCounties] = useState(false)
  const [countyError, setCountyError] = useState<string | null>(null)

  const [listingMode, setListingMode] = useState<ListingMode>('buy')
  const [filters, setFilters] = useState<SearchCriteria>(loadSavedFilters)
  const [selected, setSelected] = useState<Property | null>(null)
  const [filterOpen, setFilterOpen] = useState(false)

  // Load meta.json once on mount — tiny file, shows county counts in sidebar
  useEffect(() => {
    const base = import.meta.env.BASE_URL
    fetch(`${base}data/meta.json`)
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
      .then(setMeta)
      .catch(e => setMetaError(String(e)))
      .finally(() => setLoadingMeta(false))
  }, [])

  // Persist filters to localStorage
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(filters))
    } catch {}
  }, [filters])

  // Clear county selection and listings when mode changes
  useEffect(() => {
    setFilters(f => ({ ...f, counties: [] }))
    setListings([])
    setCountyError(null)
  }, [listingMode])

  // Stable string key so the fetch effect doesn't fire on every render
  const countiesKey = useMemo(
    () => [...filters.counties].sort().join(','),
    [filters.counties],
  )

  // Fetch only the selected county files in parallel when county selection changes
  useEffect(() => {
    if (!countiesKey) {
      setListings([])
      setCountyError(null)
      return
    }
    const keys = countiesKey.split(',')
    setLoadingCounties(true)
    setCountyError(null)
    const base = import.meta.env.BASE_URL
    const dataPath = listingMode === 'rent' ? 'data/rentals' : 'data/counties'
    Promise.all(
      keys.map(key =>
        fetch(`${base}${dataPath}/${key}.json`)
          .then(r => {
            if (!r.ok) throw new Error(`HTTP ${r.status} fetching ${key}`)
            return r.json() as Promise<Property[]>
          }),
      ),
    )
      .then(arrays => {
        // Merge and deduplicate cross-county listings by fingerprint
        const map = new Map<string, Property>()
        for (const arr of arrays) {
          for (const p of arr) {
            if (!map.has(p.fingerprint)) map.set(p.fingerprint, p)
          }
        }
        setListings(Array.from(map.values()))
      })
      .catch(e => setCountyError(String(e)))
      .finally(() => setLoadingCounties(false))
  }, [countiesKey, listingMode])

  const filtered = useMemo(
    () => applyFilters(listings, filters),
    [listings, filters],
  )

  const noCountySelected = !loadingMeta && !metaError && filters.counties.length === 0

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      {/* Topbar */}
      <header className="flex items-center justify-between px-4 py-3 bg-slate-950 border-b border-slate-800 flex-shrink-0">
        <div className="flex items-center gap-3">
          <span className="font-bold text-lg text-white tracking-tight">HomeFinder</span>
          <span className="hidden sm:inline text-xs text-slate-500 border border-slate-800 rounded px-2 py-0.5">
            Tri-State · Daily Updated
          </span>
        </div>
        {/* Buy / Rent toggle */}
        <div className="flex gap-0.5 bg-slate-800 rounded-lg p-0.5">
          {(['buy', 'rent'] as const).map(m => (
            <button
              key={m}
              onClick={() => setListingMode(m)}
              className={`px-3 py-1 rounded-md text-sm font-medium transition-colors ${
                listingMode === m
                  ? 'bg-slate-600 text-white'
                  : 'text-slate-400 hover:text-slate-300'
              }`}
            >
              {m === 'buy' ? 'Buy' : 'Rent'}
            </button>
          ))}
        </div>
        {/* Mobile filter toggle */}
        <button
          className="lg:hidden flex items-center gap-1.5 text-sm text-slate-300 bg-slate-800 px-3 py-1.5 rounded-lg border border-slate-700"
          onClick={() => setFilterOpen(true)}
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 4h18M6 8h12M9 12h6" />
          </svg>
          Filters
          {isFiltered(filters) && (
            <span className="w-1.5 h-1.5 bg-blue-400 rounded-full" />
          )}
        </button>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar — desktop */}
        <aside className="hidden lg:flex flex-col w-72 xl:w-80 flex-shrink-0 overflow-hidden">
          <FilterPanel
            filters={filters}
            onChange={setFilters}
            resultCount={filtered.length}
            meta={meta}
            listingMode={listingMode}
          />
        </aside>

        {/* Main content */}
        <main className="flex-1 flex flex-col overflow-hidden">
          <StatsBar
            filtered={filtered}
            total={listings.length}
            meta={meta}
            listingMode={listingMode}
          />

          {/* Meta load error */}
          {metaError && (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center max-w-sm px-6">
                <p className="text-2xl mb-2">⚠️</p>
                <p className="text-slate-300 font-medium mb-1">Couldn't load app data</p>
                <p className="text-slate-500 text-sm">{metaError}</p>
              </div>
            </div>
          )}

          {/* Empty state: pick a county to start */}
          {noCountySelected && (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center max-w-sm px-6">
                <p className="text-4xl mb-3">🗺️</p>
                <p className="text-slate-300 font-semibold mb-2">Select a county to get started</p>
                <p className="text-slate-500 text-sm mb-5">
                  Choose one or more counties from the sidebar, or load an entire state below.
                </p>
                <div className="flex gap-2 justify-center flex-wrap">
                  {COUNTY_GROUPS.map(g => (
                    <button
                      key={g.abbr}
                      onClick={() => setFilters(f => ({ ...f, counties: g.keys }))}
                      className="text-sm px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition-colors"
                    >
                      All {g.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Loading county files */}
          {loadingCounties && (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
                <p className="text-slate-400 text-sm">
                  Loading {filters.counties.length} county file{filters.counties.length !== 1 ? 's' : ''}…
                </p>
              </div>
            </div>
          )}

          {/* County fetch error */}
          {countyError && !loadingCounties && (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center max-w-sm px-6">
                <p className="text-2xl mb-2">⚠️</p>
                <p className="text-slate-300 font-medium mb-1">Couldn't load listings</p>
                <p className="text-slate-500 text-sm">{countyError}</p>
                <p className="text-slate-600 text-xs mt-3">
                  The scraper may not have run yet. Try again after the next GitHub Actions run.
                </p>
              </div>
            </div>
          )}

          {/* No filter matches */}
          {!loadingCounties && !countyError && filters.counties.length > 0 && listings.length > 0 && filtered.length === 0 && (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center max-w-sm px-6">
                <p className="text-4xl mb-3">🏠</p>
                <p className="text-slate-300 font-medium mb-1">No listings match your filters</p>
                <p className="text-slate-500 text-sm">Try broadening your search criteria.</p>
              </div>
            </div>
          )}

          {/* Results — virtual list renders only ~20 cards at a time */}
          {!loadingCounties && !countyError && filtered.length > 0 && (
            <div className="flex-1 min-h-0">
              <Virtuoso
                style={{ height: '100%' }}
                data={filtered}
                itemContent={(_, p) => (
                  <div className="px-3 pt-2">
                    <PropertyCard property={p} onSelect={setSelected} listingMode={listingMode} />
                  </div>
                )}
                components={{
                  Footer: () => (
                    <p className="text-center text-slate-700 text-xs py-4">
                      — {filtered.length.toLocaleString()} listings —
                    </p>
                  ),
                }}
              />
            </div>
          )}
        </main>
      </div>

      {/* Mobile filter drawer */}
      {filterOpen && (
        <div className="lg:hidden fixed inset-0 z-40 flex">
          <div className="absolute inset-0 bg-black/60" onClick={() => setFilterOpen(false)} />
          <div className="relative w-80 max-w-full ml-auto h-full flex flex-col">
            <FilterPanel
              filters={filters}
              onChange={setFilters}
              resultCount={filtered.length}
              meta={meta}
              listingMode={listingMode}
              onClose={() => setFilterOpen(false)}
            />
          </div>
        </div>
      )}

      {/* Property detail modal */}
      {selected && (
        <PropertyDetail
          property={selected}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  )
}

function isFiltered(f: SearchCriteria): boolean {
  return (
    f.query !== '' ||
    f.minPrice !== null ||
    f.maxPrice !== null ||
    f.minBeds !== null ||
    f.minBaths !== null ||
    f.minSqft !== null ||
    f.maxSqft !== null ||
    f.propertyTypes.length > 0 ||
    f.maxHoa !== null ||
    f.maxDom !== null ||
    JSON.stringify(f.statuses) !== JSON.stringify(DEFAULT_FILTERS.statuses)
  )
}
