import { memo } from 'react'
import type { Property } from '../types'
import { fmtPrice, fmtNum, STATUS_CONFIG, TYPE_LABELS } from '../types'

interface Props {
  property: Property
  onSelect: (p: Property) => void
}

function PropertyCard({ property: p, onSelect }: Props) {
  const status = STATUS_CONFIG[p.status] ?? STATUS_CONFIG['active']
  const isNew = p.days_on_market !== null && p.days_on_market <= 3

  return (
    <div
      onClick={() => onSelect(p)}
      className="bg-slate-900 border border-slate-800 rounded-xl p-4 cursor-pointer hover:border-slate-600 hover:bg-slate-800/80 transition-colors active:scale-[0.99]"
    >
      {/* Top row: address + price */}
      <div className="flex items-start justify-between gap-3 mb-2.5">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5 mb-0.5">
            <span className={`text-xs font-medium ${status.color} ${status.bg} px-1.5 py-0.5 rounded`}>
              {status.label}
            </span>
            {isNew && (
              <span className="text-xs font-semibold text-green-400 bg-green-500/10 px-1.5 py-0.5 rounded">
                NEW
              </span>
            )}
          </div>
          <p className="font-medium text-white text-sm truncate">{p.address}</p>
          <p className="text-slate-400 text-xs mt-0.5">
            {TYPE_LABELS[p.property_type] ?? p.property_type} · {p.city}, {p.state} {p.zip_code}
          </p>
        </div>
        <div className="text-right flex-shrink-0">
          <p className="font-bold text-white text-base">{fmtPrice(p.price)}</p>
          {p.price_per_sqft !== null && (
            <p className="text-xs text-slate-500">${fmtNum(p.price_per_sqft)}/ft²</p>
          )}
        </div>
      </div>

      {/* Stats row */}
      <div className="flex items-center gap-3 text-xs text-slate-400 flex-wrap">
        {p.beds !== null && (
          <Stat value={`${p.beds}`} label="bd" />
        )}
        {p.baths !== null && (
          <Stat value={`${p.baths}`} label="ba" />
        )}
        {p.sqft !== null && (
          <Stat value={fmtNum(p.sqft)} label="ft²" />
        )}
        {p.hoa_monthly !== null && p.hoa_monthly > 0 && (
          <span className="text-slate-500">HOA ${fmtNum(p.hoa_monthly)}/mo</span>
        )}
        {p.year_built !== null && (
          <span className="text-slate-500">Built {p.year_built}</span>
        )}
        {p.lot_sqft !== null && p.lot_sqft > 0 && (
          <span className="text-slate-500">{fmtNum(p.lot_sqft)} lot</span>
        )}
        {p.days_on_market !== null && (
          <span className={`ml-auto ${p.days_on_market <= 7 ? 'text-green-400 font-medium' : 'text-slate-600'}`}>
            {p.days_on_market === 0 ? 'Today' : `${p.days_on_market}d`}
          </span>
        )}
      </div>
    </div>
  )
}

export default memo(PropertyCard)

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <span>
      <span className="text-slate-200 font-medium">{value}</span>
      <span className="ml-0.5 text-slate-500">{label}</span>
    </span>
  )
}
