// Shared between the build and the browser (no Node imports here).
export type Listing = {
  id: string;
  agent: string;
  url: string;
  category: 'residential' | 'commercial' | 'land';
  listingType: 'sale' | 'rent';
  price: number | null;
  priceQualifier: string;
  priceNote?: string;
  previousPrice?: number;
  bedrooms: number | null;
  bathrooms: number | null;
  propertyType: string | null;
  address: string;
  locality: string | null;
  parish: string | null;
  status?: string;
  firstSeen?: string;
};

export function statusLabel(s?: string): { text: string; kind: 'warn' | 'bad' | 'info' } | null {
  const v = String(s || '').toLowerCase().replace(/[_-]/g, ' ').trim();
  if (!v || v === 'for sale' || v === 'let' || v === 'to let' || v === 'available' || v === 'updated') return null;
  if (v.includes('sold')) return { text: 'Sold STC', kind: 'bad' };
  if (v.includes('offer accepted')) return { text: 'Offer accepted', kind: 'warn' };
  if (v.includes('under offer')) return { text: 'Under offer', kind: 'warn' };
  if (v.includes('let stc') || v.includes('let agreed')) return { text: 'Let agreed', kind: 'bad' };
  if (v.includes('reserved')) return { text: 'Reserved', kind: 'warn' };
  return { text: s!, kind: 'info' };
}

const Q: Record<string, string> = {
  guide: 'Guide price',
  oio: 'Offers in the region of',
  oieo: 'Offers in excess of',
  'offers-around': 'Offers around',
};

export function priceText(l: Listing): { main: string; prefix?: string; note?: string } {
  if (l.price == null) {
    return { main: l.priceNote || 'POA', note: l.priceNote && l.priceNote !== 'POA' ? undefined : undefined };
  }
  const n = '£' + Math.round(l.price).toLocaleString('en-GB');
  if (l.listingType === 'rent') {
    const per = l.priceQualifier === 'pa' ? ' a year' : ' pcm';
    return { main: n + per, note: l.priceNote };
  }
  return { main: n, prefix: Q[l.priceQualifier], note: l.priceNote };
}

export function typeLabel(l: Listing): string {
  const t = (l.propertyType || '').replace(/-/g, ' ');
  const beds = l.bedrooms ? `${l.bedrooms} bed ` : '';
  if (t) return beds + t;
  return beds + (l.category === 'land' ? 'land' : l.category === 'commercial' ? 'commercial property' : 'property');
}

export function place(l: Listing): string {
  const s = (l.locality || l.parish || '').replace(/^Port St\. Mary$/, 'Port St Mary').replace(/^St\. John's$/, 'St Johns').replace(/^St\. Mark's$/, 'St Marks');
  return s;
}
