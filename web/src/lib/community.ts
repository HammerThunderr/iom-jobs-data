// Approved community events, read through Firestore's public REST API so the
// What's On page doesn't need the Firebase SDK. (Submitting uses the SDK; see
// community-auth.ts.)
export const FIREBASE = {
  apiKey: 'AIzaSyARM9cnLTXXViei3aKNaiRtRO2VpDELSfQ',
  appId: '1:189093862843:web:62d406ff93797a9a0b389e',
  messagingSenderId: '189093862843',
  projectId: 'iom-jobs-b7eab',
  authDomain: 'iom-jobs-b7eab.firebaseapp.com',
  storageBucket: 'iom-jobs-b7eab.firebasestorage.app',
};

export type CommunityEvent = {
  id: string;
  title: string;
  venue: string;
  area: string;
  category: string;
  startDate: string;
  endDate: string;
  startTime: string;
  endTime: string;
  description: string;
  price: string;
  url: string;
  imageUrl: string;
  organiser: string;
};

function val(v: any): any {
  if (!v) return '';
  if ('stringValue' in v) return v.stringValue;
  if ('integerValue' in v) return Number(v.integerValue);
  if ('doubleValue' in v) return v.doubleValue;
  if ('booleanValue' in v) return v.booleanValue;
  if ('timestampValue' in v) return v.timestampValue;
  return '';
}

export function fromDoc(doc: any): CommunityEvent {
  const f = doc.fields || {};
  const g = (k: string) => String(val(f[k]) ?? '');
  return {
    id: String(doc.name || '').split('/').pop() || '',
    title: g('title'),
    venue: g('venue'),
    area: g('area'),
    category: g('category') || 'Community',
    startDate: g('startDate'),
    endDate: g('endDate') || g('startDate'),
    startTime: g('startTime'),
    endTime: g('endTime'),
    description: g('description'),
    price: g('price'),
    url: g('url'),
    imageUrl: g('imageUrl'),
    organiser: g('organiser'),
  };
}

const BASE = `https://firestore.googleapis.com/v1/projects/${FIREBASE.projectId}/databases/(default)/documents`;

export async function loadCommunityEvents(): Promise<CommunityEvent[]> {
  const today = new Date().toLocaleDateString('en-CA', { timeZone: 'Europe/London' });
  const res = await fetch(`${BASE}:runQuery?key=${FIREBASE.apiKey}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      structuredQuery: {
        from: [{ collectionId: 'community_events' }],
        where: { fieldFilter: { field: { fieldPath: 'endDate' }, op: 'GREATER_THAN_OR_EQUAL', value: { stringValue: today } } },
        limit: 200,
      },
    }),
  });
  if (!res.ok) return [];
  const rows = await res.json();
  return (rows || []).filter((r: any) => r.document).map((r: any) => fromDoc(r.document)).sort((a: CommunityEvent, b: CommunityEvent) => a.startDate.localeCompare(b.startDate));
}

export async function loadCommunityEvent(id: string): Promise<CommunityEvent | null> {
  const res = await fetch(`${BASE}/community_events/${encodeURIComponent(id)}?key=${FIREBASE.apiKey}`);
  if (!res.ok) return null;
  return fromDoc(await res.json());
}

export const AREAS = ['Douglas', 'Peel', 'Ramsey', 'Castletown', 'Port Erin', 'Laxey', 'Kirk Michael', 'Islandwide'];
