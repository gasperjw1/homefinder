import type { Property } from '../types'
import { fmtPrice, fmtNum, STATUS_CONFIG, TYPE_LABELS } from '../types'

interface Props {
  property: Property
  onClose: () => void
}

export default function PropertyDetail({ property: p, onClose }: Props) {
  const status = STATUS_CONFIG[p.status] ?? STATUS_CONFIG['active']

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/70" onClick={onClose}>
      <div
        className="bg-slate-900 border border-slate-700 rounded-t-2xl sm:rounded-2xl w-full sm:max-w-lg max-h-[90vh] overflow-y-auto scrollbar-thin"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="sticky top-0 bg-slate-900 border-b border-slate-800 px-5 py-4 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <span className={`text-xs font-medium ${status.color} ${status.bg} px-1.5 py-0.5 rounded`}>
                {status.label}
              </span>
              <span className="text-xs text-slate-500">
                {TYPE_LABELS[p.property_type] ?? p.property_type}
              </span>
            </div>
            <h2 className="font-semibold text-white text-base leading-snug">{p.address}</h2>
            <p className="text-slate-400 text-sm">{p.city}, {p.state} {p.zip_code}</p>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white text-2xl leading-none flex-shrink-0 mt-0.5"
          >
            ×
          </button>
        </div>

        {/* Price block */}
        <div className="px-5 py-4 border-b border-slate-800">
          <p className="text-2xl font-bold text-white">{fmtPrice(p.price)}</p>
          {p.price_per_sqft !== null && (
            <p className="text-sm text-slate-400 mt-0.5">${fmtNum(p.price_per_sqft)} per ft²</p>
          )}
        </div>

        {/* Key stats grid */}
        <div className="grid grid-cols-3 gap-px bg-slate-800 border-b border-slate-800">
          <StatCell label="Beds" value={p.beds !== null ? String(p.beds) : '—'} />
          <StatCell label="Baths" value={p.baths !== null ? String(p.baths) : '—'} />
          <StatCell label="Sqft" value={p.sqft !== null ? fmtNum(p.sqft) : '—'} />
        </div>

        {/* Details list */}
        <div className="px-5 py-4 space-y-3">
          <DetailRow label="Year Built" value={p.year_built ? String(p.year_built) : null} />
          <DetailRow label="HOA / month" value={p.hoa_monthly ? `$${fmtNum(p.hoa_monthly)}` : null} />
          <DetailRow label="Lot Size" value={p.lot_sqft && p.lot_sqft > 0 ? `${fmtNum(p.lot_sqft)} ft²` : null} />
          <DetailRow label="Days on Market" value={p.days_on_market !== null ? (p.days_on_market === 0 ? 'Listed today' : `${p.days_on_market} days`) : null} />
          <DetailRow label="MLS #" value={p.mls_id} />
          <DetailRow label="Source" value={p.source.charAt(0).toUpperCase() + p.source.slice(1)} />
          {p.walk_score !== null && (
            <DetailRow label="Walk Score" value={`${p.walk_score}/100`} />
          )}
          {p.transit_score !== null && (
            <DetailRow label="Transit Score" value={`${p.transit_score}/100`} />
          )}
        </div>

        {/* Description */}
        {p.description && (
          <div className="px-5 pb-4">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">Description</p>
            <p className="text-sm text-slate-300 leading-relaxed">{p.description}</p>
          </div>
        )}

        {/* View on Redfin */}
        {p.url && (
          <div className="px-5 pb-5">
            <a
              href={p.url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center justify-center gap-2 w-full bg-blue-600 hover:bg-blue-500 text-white font-semibold py-3 rounded-xl text-sm transition-colors"
            >
              View on Redfin
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
            </a>
          </div>
        )}
      </div>
    </div>
  )
}

function StatCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-slate-900 px-4 py-3 text-center">
      <p className="text-lg font-bold text-white">{value}</p>
      <p className="text-xs text-slate-500 mt-0.5">{label}</p>
    </div>
  )
}

function DetailRow({ label, value }: { label: string; value: string | null | undefined }) {
  if (!value) return null
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-slate-500">{label}</span>
      <span className="text-slate-200 font-medium">{value}</span>
    </div>
  )
}
