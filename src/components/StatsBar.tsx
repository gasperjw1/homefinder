import type { Property, ListingsMeta } from '../types'
import { fmtPrice, fmtNum } from '../types'

interface Props {
  filtered: Property[]
  total: number
  meta: ListingsMeta | null
  listingMode: 'buy' | 'rent'
}

export default function StatsBar({ filtered, total, meta, listingMode }: Props) {
  const prices = filtered.map(p => p.price).filter((p): p is number => p !== null)
  const ppsf = filtered.map(p => p.price_per_sqft).filter((p): p is number => p !== null)

  let minPrice = Infinity, maxPrice = -Infinity
  for (const v of prices) { if (v < minPrice) minPrice = v; if (v > maxPrice) maxPrice = v }

  const avgPpsf = ppsf.length > 0 ? Math.round(ppsf.reduce((a, b) => a + b, 0) / ppsf.length) : null

  const lastUpdated = meta?.last_updated
    ? new Date(meta.last_updated).toLocaleDateString('en-US', {
        month: 'short', day: 'numeric', year: 'numeric',
      })
    : null

  return (
    <div className="flex items-center gap-4 px-4 py-2.5 bg-slate-900/60 border-b border-slate-800 text-sm overflow-x-auto whitespace-nowrap scrollbar-thin">
      <span className="font-semibold text-white">
        {fmtNum(filtered.length)}
        <span className="font-normal text-slate-500 ml-1">
          {filtered.length !== total ? `of ${fmtNum(total)}` : ''} listings
        </span>
      </span>

      {prices.length > 0 && (
        <>
          <Divider />
          <Stat
            label={listingMode === 'rent' ? 'Rent range' : 'Range'}
            value={`${fmtPrice(minPrice === Infinity ? null : minPrice)} – ${fmtPrice(maxPrice === -Infinity ? null : maxPrice)}`}
          />
        </>
      )}

      {avgPpsf !== null && listingMode === 'buy' && (
        <>
          <Divider />
          <Stat label="Avg $/ft²" value={`$${fmtNum(avgPpsf)}`} />
        </>
      )}

      {lastUpdated && (
        <>
          <Divider />
          <span className="text-slate-500 text-xs ml-auto">Updated {lastUpdated}</span>
        </>
      )}
    </div>
  )
}

function Divider() {
  return <span className="text-slate-700">·</span>
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <span className="text-slate-400">
      {label}: <span className="text-slate-200">{value}</span>
    </span>
  )
}
