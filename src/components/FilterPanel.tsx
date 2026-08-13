import { type SearchCriteria, type ListingsMeta, DEFAULT_FILTERS, PROPERTY_TYPES, STATUSES, COUNTY_GROUPS, countyLabel, AMENITY_TAGS } from '../types'

interface Props {
  filters: SearchCriteria
  onChange: (f: SearchCriteria) => void
  resultCount: number
  meta: ListingsMeta | null
  listingMode: 'buy' | 'rent'
  onClose?: () => void
}

export default function FilterPanel({ filters, onChange, resultCount, meta, listingMode, onClose }: Props) {
  const set = <K extends keyof SearchCriteria>(key: K, value: SearchCriteria[K]) =>
    onChange({ ...filters, [key]: value })

  const isDefault = JSON.stringify(filters) === JSON.stringify(DEFAULT_FILTERS)

  return (
    <div className="flex flex-col h-full bg-slate-900 border-r border-slate-800">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800">
        <h2 className="font-semibold text-white">Filters</h2>
        <div className="flex items-center gap-2">
          {!isDefault && (
            <button
              onClick={() => onChange(DEFAULT_FILTERS)}
              className="text-xs text-blue-400 hover:text-blue-300"
            >
              Reset
            </button>
          )}
          {onClose && (
            <button
              onClick={onClose}
              className="text-slate-400 hover:text-white ml-2 text-lg leading-none"
            >
              ×
            </button>
          )}
        </div>
      </div>

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto scrollbar-thin px-4 py-4 space-y-6">

        {/* Location */}
        <Section label="Location">
          <CountyPicker
            selected={filters.counties}
            onChange={v => set('counties', v)}
            meta={meta}
          />
        </Section>

        {/* Search */}
        <Section label="Search">
          <input
            type="text"
            placeholder="City, ZIP, or address..."
            value={filters.query}
            onChange={e => set('query', e.target.value)}
            className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500"
          />
        </Section>

        {/* Sort */}
        <Section label="Sort by">
          <select
            value={filters.sortBy}
            onChange={e => set('sortBy', e.target.value as SearchCriteria['sortBy'])}
            className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
          >
            <option value="price_asc">{listingMode === 'rent' ? 'Rent: Low to High' : 'Price: Low to High'}</option>
            <option value="price_desc">{listingMode === 'rent' ? 'Rent: High to Low' : 'Price: High to Low'}</option>
            <option value="newest">Newest Listed</option>
            {listingMode === 'buy' && <option value="value">Best Value ($/ft²)</option>}
          </select>
        </Section>

        {/* Price / Rent */}
        <Section label={listingMode === 'rent' ? 'Monthly Rent' : 'Price'}>
          <div className="flex gap-2">
            <NumInput
              placeholder="Min"
              value={filters.minPrice}
              onChange={v => set('minPrice', v)}
              prefix="$"
            />
            <NumInput
              placeholder="Max"
              value={filters.maxPrice}
              onChange={v => set('maxPrice', v)}
              prefix="$"
            />
          </div>
        </Section>

        {/* Beds */}
        <Section label="Bedrooms">
          <div className="flex gap-1.5">
            {[null, 1, 2, 3, 4, 5].map(n => (
              <button
                key={String(n)}
                onClick={() => set('minBeds', filters.minBeds === n ? null : n)}
                className={`flex-1 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                  filters.minBeds === n
                    ? 'bg-blue-600 text-white'
                    : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
                }`}
              >
                {n === null ? 'Any' : `${n}+`}
              </button>
            ))}
          </div>
        </Section>

        {/* Baths */}
        <Section label="Bathrooms">
          <div className="flex gap-1.5">
            {[null, 1, 1.5, 2, 3].map(n => (
              <button
                key={String(n)}
                onClick={() => set('minBaths', filters.minBaths === n ? null : n)}
                className={`flex-1 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                  filters.minBaths === n
                    ? 'bg-blue-600 text-white'
                    : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
                }`}
              >
                {n === null ? 'Any' : `${n}+`}
              </button>
            ))}
          </div>
        </Section>

        {/* Sqft */}
        <Section label="Square Footage">
          <div className="flex gap-2">
            <NumInput
              placeholder="Min"
              value={filters.minSqft}
              onChange={v => set('minSqft', v)}
              suffix="ft²"
            />
            <NumInput
              placeholder="Max"
              value={filters.maxSqft}
              onChange={v => set('maxSqft', v)}
              suffix="ft²"
            />
          </div>
        </Section>

        {/* Amenities */}
        <Section label="Amenities">
          <div className="flex flex-wrap gap-1.5">
            {AMENITY_TAGS.map(tag => {
              const active = filters.amenities.includes(tag.label)
              return (
                <button
                  key={tag.label}
                  onClick={() => {
                    const next = active
                      ? filters.amenities.filter(a => a !== tag.label)
                      : [...filters.amenities, tag.label]
                    set('amenities', next)
                  }}
                  className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${
                    active
                      ? 'bg-blue-600 border-blue-600 text-white'
                      : 'border-slate-600 text-slate-400 hover:border-slate-400 hover:text-slate-300'
                  }`}
                >
                  {tag.label}
                </button>
              )
            })}
          </div>
        </Section>

        {/* Status — buy only */}
        {listingMode === 'buy' && (
        <Section label="Status">
          <div className="flex flex-col gap-1.5">
            {STATUSES.map(s => (
              <CheckItem
                key={s.value}
                label={s.label}
                checked={filters.statuses.includes(s.value)}
                onChange={on => {
                  const next = on
                    ? [...filters.statuses, s.value]
                    : filters.statuses.filter(x => x !== s.value)
                  set('statuses', next)
                }}
              />
            ))}
          </div>
        </Section>
        )}

        {/* Property Type — buy only */}
        {listingMode === 'buy' && (
        <Section label="Property Type">
          <div className="flex flex-col gap-1.5">
            {PROPERTY_TYPES.map(t => (
              <CheckItem
                key={t.value}
                label={t.label}
                checked={filters.propertyTypes.includes(t.value)}
                onChange={on => {
                  const next = on
                    ? [...filters.propertyTypes, t.value]
                    : filters.propertyTypes.filter(x => x !== t.value)
                  set('propertyTypes', next)
                }}
              />
            ))}
          </div>
        </Section>
        )}

        {/* Max HOA — buy only */}
        {listingMode === 'buy' && (
        <Section label="Max HOA / month">
          <NumInput
            placeholder="e.g. 500"
            value={filters.maxHoa}
            onChange={v => set('maxHoa', v)}
            prefix="$"
            className="w-full"
          />
        </Section>
        )}

        {/* Days on Market */}
        <Section label="Max Days on Market">
          <NumInput
            placeholder="e.g. 30"
            value={filters.maxDom}
            onChange={v => set('maxDom', v)}
            suffix="days"
            className="w-full"
          />
        </Section>
      </div>

      {/* Footer: apply button on mobile */}
      {onClose && (
        <div className="p-4 border-t border-slate-800">
          <button
            onClick={onClose}
            className="w-full bg-blue-600 hover:bg-blue-500 text-white font-semibold py-2.5 rounded-xl text-sm"
          >
            Show {resultCount.toLocaleString()} listings
          </button>
        </div>
      )}
    </div>
  )
}

function CountyPicker({
  selected, onChange, meta,
}: {
  selected: string[]
  onChange: (counties: string[]) => void
  meta: ListingsMeta | null
}) {
  const toggle = (key: string) =>
    onChange(selected.includes(key) ? selected.filter(k => k !== key) : [...selected, key])

  const toggleGroup = (keys: string[]) => {
    const allOn = keys.every(k => selected.includes(k))
    onChange(allOn ? selected.filter(k => !keys.includes(k)) : [...new Set([...selected, ...keys])])
  }

  return (
    <div className="space-y-3">
      {/* State quick-select pills */}
      <div className="flex gap-1.5 items-center">
        {COUNTY_GROUPS.map(g => {
          const allOn = g.keys.every(k => selected.includes(k))
          return (
            <button
              key={g.abbr}
              onClick={() => toggleGroup(g.keys)}
              className={`text-xs px-3 py-1 rounded-full border transition-colors ${
                allOn
                  ? 'bg-blue-600 border-blue-600 text-white'
                  : 'border-slate-600 text-slate-400 hover:border-slate-400 hover:text-slate-300'
              }`}
            >
              {g.abbr}
            </button>
          )
        })}
        {selected.length > 0 && (
          <button
            onClick={() => onChange([])}
            className="text-xs text-slate-500 hover:text-slate-300 ml-auto"
          >
            Clear
          </button>
        )}
      </div>

      {/* Grouped checkboxes */}
      {COUNTY_GROUPS.map(g => (
        <div key={g.label}>
          <p className="text-xs text-slate-600 uppercase tracking-wide font-semibold mb-1">{g.label}</p>
          <div className="space-y-0.5">
            {g.keys.map(key => {
              const count = meta?.counties?.[key]?.count ?? 0
              const checked = selected.includes(key)
              return (
                <div
                  key={key}
                  className="flex items-center justify-between gap-2 cursor-pointer group py-0.5"
                  onClick={() => toggle(key)}
                >
                  <div className="flex items-center gap-2.5">
                    <span
                      className={`w-4 h-4 rounded border flex items-center justify-center flex-shrink-0 transition-colors ${
                        checked ? 'bg-blue-600 border-blue-600' : 'border-slate-600 group-hover:border-slate-400'
                      }`}
                    >
                      {checked && (
                        <svg className="w-2.5 h-2.5 text-white" fill="none" viewBox="0 0 10 10">
                          <path d="M1.5 5l2.5 2.5 4.5-5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                      )}
                    </span>
                    <span className="text-sm text-slate-300 group-hover:text-white">{countyLabel(key)}</span>
                  </div>
                  {count > 0 && (
                    <span className="text-xs text-slate-600">{count.toLocaleString()}</span>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      ))}
    </div>
  )
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">{label}</p>
      {children}
    </div>
  )
}

function NumInput({
  value, onChange, placeholder, prefix, suffix, className,
}: {
  value: number | null
  onChange: (v: number | null) => void
  placeholder: string
  prefix?: string
  suffix?: string
  className?: string
}) {
  return (
    <div className={`relative ${className ?? 'flex-1'}`}>
      {prefix && (
        <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 text-sm pointer-events-none">
          {prefix}
        </span>
      )}
      <input
        type="number"
        placeholder={placeholder}
        value={value ?? ''}
        onChange={e => onChange(e.target.value ? Number(e.target.value) : null)}
        className={`w-full bg-slate-800 border border-slate-700 rounded-lg py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 ${
          prefix ? 'pl-7' : 'pl-3'
        } ${suffix ? 'pr-12' : 'pr-3'}`}
      />
      {suffix && (
        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 text-xs pointer-events-none">
          {suffix}
        </span>
      )}
    </div>
  )
}

function CheckItem({
  label, checked, onChange,
}: {
  label: string
  checked: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <label className="flex items-center gap-2.5 cursor-pointer group">
      <span
        className={`w-4 h-4 rounded border flex items-center justify-center flex-shrink-0 transition-colors ${
          checked ? 'bg-blue-600 border-blue-600' : 'border-slate-600 group-hover:border-slate-400'
        }`}
        onClick={() => onChange(!checked)}
      >
        {checked && (
          <svg className="w-2.5 h-2.5 text-white" fill="none" viewBox="0 0 10 10">
            <path d="M1.5 5l2.5 2.5 4.5-5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        )}
      </span>
      <span className="text-sm text-slate-300 group-hover:text-white">{label}</span>
    </label>
  )
}
