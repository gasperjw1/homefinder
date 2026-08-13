export interface Property {
  source: string
  source_id: string
  fingerprint: string
  address: string
  city: string
  state: string
  zip_code: string
  price: number | null
  beds: number | null
  baths: number | null
  sqft: number | null
  property_type: string
  status: string
  year_built: number | null
  hoa_monthly: number | null
  days_on_market: number | null
  lot_sqft: number | null
  latitude: number | null
  longitude: number | null
  url: string
  mls_id: string | null
  walk_score: number | null
  transit_score: number | null
  bike_score: number | null
  description: string | null
  price_per_sqft: number | null
  scraped_at: string
}

export interface CountyInfo {
  name: string
  state: string
  count: number
}

export interface ListingsMeta {
  last_updated: string | null
  total_listings: number
  source: string
  counties?: Record<string, CountyInfo>
}

export interface ListingsData {
  meta: ListingsMeta
  listings: Property[]
}

export interface SearchCriteria {
  counties: string[]
  query: string
  minPrice: number | null
  maxPrice: number | null
  minBeds: number | null
  minBaths: number | null
  minSqft: number | null
  maxSqft: number | null
  propertyTypes: string[]
  statuses: string[]
  maxHoa: number | null
  maxDom: number | null
  sortBy: 'price_asc' | 'price_desc' | 'newest' | 'value'
}

export const DEFAULT_FILTERS: SearchCriteria = {
  counties: [],
  query: '',
  minPrice: null,
  maxPrice: null,
  minBeds: null,
  minBaths: null,
  minSqft: null,
  maxSqft: null,
  propertyTypes: [],
  statuses: ['active', 'coming_soon'],
  maxHoa: null,
  maxDom: null,
  sortBy: 'price_asc',
}

export const COUNTY_GROUPS: Array<{ label: string; abbr: string; keys: string[] }> = [
  {
    label: 'New York', abbr: 'NY',
    keys: ['manhattan', 'brooklyn', 'queens', 'bronx', 'staten_island', 'westchester', 'nassau', 'suffolk', 'rockland'],
  },
  {
    label: 'New Jersey', abbr: 'NJ',
    keys: ['bergen', 'hudson', 'essex', 'passaic', 'union', 'middlesex', 'morris', 'monmouth'],
  },
  {
    label: 'Connecticut', abbr: 'CT',
    keys: ['fairfield', 'new_haven'],
  },
]

export function countyLabel(key: string): string {
  return key.split('_').map(w => w[0].toUpperCase() + w.slice(1)).join(' ')
}

export const PROPERTY_TYPES = [
  { value: 'house', label: 'House' },
  { value: 'condo', label: 'Condo' },
  { value: 'townhouse', label: 'Townhouse' },
  { value: 'multifamily', label: 'Multi-family' },
  { value: 'land', label: 'Land' },
  { value: 'other', label: 'Other' },
]

export const STATUSES = [
  { value: 'active', label: 'Active' },
  { value: 'coming_soon', label: 'Coming Soon' },
  { value: 'pending', label: 'Pending' },
  { value: 'contingent', label: 'Contingent' },
]

export function applyFilters(listings: Property[], filters: SearchCriteria): Property[] {
  let result = listings.filter(p => {
    if (filters.query) {
      const q = filters.query.toLowerCase()
      const match =
        p.address.toLowerCase().includes(q) ||
        p.city.toLowerCase().includes(q) ||
        p.zip_code.includes(q) ||
        p.state.toLowerCase().includes(q)
      if (!match) return false
    }

    if (filters.minPrice !== null && p.price !== null && p.price < filters.minPrice) return false
    if (filters.maxPrice !== null && p.price !== null && p.price > filters.maxPrice) return false
    if (filters.minBeds !== null && p.beds !== null && p.beds < filters.minBeds) return false
    if (filters.minBaths !== null && p.baths !== null && p.baths < filters.minBaths) return false
    if (filters.minSqft !== null && p.sqft !== null && p.sqft < filters.minSqft) return false
    if (filters.maxSqft !== null && p.sqft !== null && p.sqft > filters.maxSqft) return false
    if (filters.maxHoa !== null && p.hoa_monthly !== null && p.hoa_monthly > filters.maxHoa) return false
    if (filters.maxDom !== null && p.days_on_market !== null && p.days_on_market > filters.maxDom) return false

    if (filters.propertyTypes.length > 0 && !filters.propertyTypes.includes(p.property_type)) return false
    if (filters.statuses.length > 0 && !filters.statuses.includes(p.status)) return false

    return true
  })

  result.sort((a, b) => {
    switch (filters.sortBy) {
      case 'price_asc':
        return (a.price ?? Infinity) - (b.price ?? Infinity)
      case 'price_desc':
        return (b.price ?? -Infinity) - (a.price ?? -Infinity)
      case 'newest':
        return (a.days_on_market ?? Infinity) - (b.days_on_market ?? Infinity)
      case 'value':
        return (a.price_per_sqft ?? Infinity) - (b.price_per_sqft ?? Infinity)
      default:
        return 0
    }
  })

  return result
}

export function fmtPrice(n: number | null): string {
  if (n === null) return '—'
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(n % 1_000_000 === 0 ? 0 : 2)}M`
  if (n >= 1_000) return `$${(n / 1_000).toFixed(0)}K`
  return `$${n}`
}

export function fmtNum(n: number | null): string {
  if (n === null) return '—'
  return n.toLocaleString()
}

export const STATUS_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
  active:      { label: 'Active',      color: 'text-green-400',  bg: 'bg-green-500/15' },
  coming_soon: { label: 'Coming Soon', color: 'text-amber-400',  bg: 'bg-amber-500/15' },
  pending:     { label: 'Pending',     color: 'text-orange-400', bg: 'bg-orange-500/15' },
  contingent:  { label: 'Contingent',  color: 'text-orange-300', bg: 'bg-orange-500/10' },
  sold:        { label: 'Sold',        color: 'text-red-400',    bg: 'bg-red-500/15' },
}

export const TYPE_LABELS: Record<string, string> = {
  house: 'House', condo: 'Condo', townhouse: 'Townhouse',
  multifamily: 'Multi', land: 'Land', other: 'Other',
}
