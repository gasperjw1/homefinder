import { useState, useEffect, useMemo } from 'react'
import type { Property, ListingsData, SearchCriteria } from './types'
import { DEFAULT_FILTERS, applyFilters } from './types'
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
  const [data, setData] = useState<ListingsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filters, setFilters] = useState<SearchCriteria>(loadSavedFilters)
  const [selected, setSelected] = useState<Property | null>(null)
  const [filterOpen, setFilterOpen] = useState(false)

  useEffect(() => {
    const url = `${import.meta.env.BASE_URL}data/listings.json`
    fetch(url)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json() as Promise<ListingsData>
      })
      .then(setData)
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(filters))
    } catch {}
  }, [filters])

  const filtered = useMemo(
    () => applyFilters(data?.listings ?? [], filters),
    [data, filters],
  )

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
          />
        </aside>

        {/* Main content */}
        <main className="flex-1 flex flex-col overflow-hidden">
          <StatsBar
            filtered={filtered}
            total={data?.listings.length ?? 0}
            meta={data?.meta ?? null}
          />

          {loading && (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
                <p className="text-slate-400 text-sm">Loading listings...</p>
              </div>
            </div>
          )}

          {error && (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center max-w-sm px-6">
                <p className="text-2xl mb-2">⚠️</p>
                <p className="text-slate-300 font-medium mb-1">Couldn't load listings</p>
                <p className="text-slate-500 text-sm">{error}</p>
                <p className="text-slate-600 text-xs mt-3">
                  The first scrape may not have run yet. Trigger it manually via GitHub Actions.
                </p>
              </div>
            </div>
          )}

          {!loading && !error && data && filtered.length === 0 && (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center max-w-sm px-6">
                <p className="text-4xl mb-3">🏠</p>
                {data.listings.length === 0 ? (
                  <>
                    <p className="text-slate-300 font-medium mb-1">No data yet</p>
                    <p className="text-slate-500 text-sm">
                      The scraper hasn't run yet. Trigger it in GitHub Actions → Daily Listing Scrape → Run workflow.
                    </p>
                  </>
                ) : (
                  <>
                    <p className="text-slate-300 font-medium mb-1">No listings match your filters</p>
                    <p className="text-slate-500 text-sm">Try broadening your search criteria.</p>
                  </>
                )}
              </div>
            </div>
          )}

          {!loading && !error && filtered.length > 0 && (
            <div className="flex-1 overflow-y-auto scrollbar-thin px-3 py-3 space-y-2">
              {filtered.map(p => (
                <PropertyCard
                  key={p.fingerprint}
                  property={p}
                  onClick={() => setSelected(p)}
                />
              ))}
              <p className="text-center text-slate-700 text-xs py-4">
                — {filtered.length.toLocaleString()} listings —
              </p>
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
