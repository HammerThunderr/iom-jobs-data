// Live ferry and flight data: the app's Cloudflare workers first, then the
// scraped JSON in the data repo. Browser-only.
import { getData, getJson } from './client';

export type Flight = { flightNo: string; airline: string; scheduled: string; status: string; statusType: string; place: string };
export type Sailing = { departTime: string; departPort: string; arriveTime: string; arrivePort: string; ferry: string; status: string; statusType: string };

const pick = (o: any, keys: string[]) => {
  for (const k of keys) {
    const v = o?.[k];
    if (v != null && String(v).trim()) return String(v).trim();
  }
  return '';
};

function flightType(status: string, sev: string) {
  const t = status.toLowerCase();
  if (t.includes('cancel')) return 'cancelled';
  if (t.includes('delay')) return 'delayed';
  if (t.includes('depart')) return 'departed';
  if (t.includes('arriv') || t.includes('landed')) return 'arrived';
  if (t.includes('board') || t.includes('gate')) return 'boarding';
  if (t.replace(/[-\s]/g, '').includes('ontime')) return 'ontime';
  if (sev === 'danger') return 'cancelled';
  if (sev === 'warning') return 'delayed';
  return 'scheduled';
}

function normFlight(r: any, dep: boolean): Flight {
  let status = pick(r, ['status', 'statusText']);
  const actual = pick(r, ['actualTime', 'estimated', 'revised']);
  if (actual && !status.includes(actual)) status = status ? `${status} ${actual}` : actual;
  let st = pick(r, ['statusType', 'severity']);
  if (!st || ['success', 'warning', 'danger'].includes(st)) st = flightType(status, st);
  return {
    flightNo: pick(r, ['flightNo', 'flightNumber', 'flight', 'number']),
    airline: pick(r, ['airline', 'carrier', 'operator']),
    scheduled: pick(r, ['scheduled', 'scheduledTime', 'time', 'sta', 'std']),
    status,
    statusType: st,
    place: pick(r, [dep ? 'destination' : 'origin', 'airport', 'city', dep ? 'to' : 'from']),
  };
}

export async function fetchFlights(): Promise<{ departures: Flight[]; arrivals: Flight[]; updated: string; live: boolean }> {
  try {
    const j = await getJson<any>('https://manxone-flights.hammerpunch786.workers.dev', 7000);
    if (j.success) {
      const departures = (j.departures || []).map((r: any) => normFlight(r, true));
      const arrivals = (j.arrivals || []).map((r: any) => normFlight(r, false));
      if (departures.length || arrivals.length) return { departures, arrivals, updated: j.fetchedAt || '', live: j.source !== 'cache' };
    }
  } catch {}
  const j = await getData<any>('flights.json');
  return {
    departures: (j.departures || []).map((r: any) => normFlight(r, true)),
    arrivals: (j.arrivals || []).map((r: any) => normFlight(r, false)),
    updated: j.fetchedAt || '',
    live: false,
  };
}

function ferryType(status: string) {
  const t = status.toLowerCase();
  if (t.includes('cancel')) return 'cancelled';
  if (t.includes('delay')) return 'delayed';
  if (t.includes('arrived')) return 'arrived';
  if (t.includes('departed') || t.includes('at sea')) return 'departed';
  if (t.includes('board') || t.includes('berthed')) return 'boarding';
  return 'scheduled';
}

function normSailing(r: any): Sailing {
  let status = pick(r, ['status', 'statusText']);
  if (r.arrivalIsEstimate === true && status) status += ' · ETA';
  return {
    departTime: pick(r, ['departTime', 'departure', 'depart', 'std']),
    departPort: pick(r, ['departPort', 'from', 'origin']),
    arriveTime: pick(r, ['arriveTime', 'arrival', 'arrive', 'sta']),
    arrivePort: pick(r, ['arrivePort', 'to', 'destination']),
    ferry: pick(r, ['ferry', 'vessel', 'ship']),
    status,
    statusType: pick(r, ['statusType', 'severity']) || ferryType(status),
  };
}

export type FerryDay = { date: string; iso: string; sailings: Sailing[] };

function isoFromLabel(label: string): string {
  const d = new Date(label.replace(/^\w+,\s*/, '') + ' 12:00 UTC');
  return isNaN(d.getTime()) ? '' : d.toISOString().slice(0, 10);
}

export async function fetchFerry(): Promise<{ days: FerryDay[]; updated: string; notice: string; live: boolean }> {
  let fallbackNotice = '';
  try {
    const j = await getJson<any>('https://manxone-sailings.hammerpunch786.workers.dev', 7000);
    if (j.success && Array.isArray(j.sailings) && j.sailings.length) {
      const map = new Map<string, Sailing[]>();
      for (const s of j.sailings) {
        const iso = String(s.date || '').slice(0, 10);
        if (!map.has(iso)) map.set(iso, []);
        map.get(iso)!.push(normSailing(s));
      }
      let notice = String(j.notice || '').trim();
      if (notice && (notice.endsWith(':') || notice.length < 30)) notice = '';
      const days = [...map.entries()].sort().map(([iso, sailings]) => ({ iso, date: new Date(iso + 'T12:00:00Z').toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }), sailings }));
      return { days, updated: j.siteUpdated || j.fetchedAtLocal || '', notice, live: j.source !== 'cache' };
    }
  } catch {}
  const j = await getData<any>('ferry.json');
  fallbackNotice = j.notice || '';
  return {
    days: (j.days || []).map((d: any) => ({ date: d.date, iso: isoFromLabel(d.date), sailings: (d.sailings || []).map(normSailing) })),
    updated: j.lastUpdated || '',
    notice: fallbackNotice,
    live: false,
  };
}

export function statusClass(t: string): string {
  return ({ cancelled: 'bad', delayed: 'warn', departed: 'info', arrived: 'ok', boarding: 'warn', ontime: 'ok', scheduled: '' } as Record<string, string>)[t] ?? '';
}
