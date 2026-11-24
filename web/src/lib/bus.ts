// Bus timetables, day patterns and the journey planner, ported from the
// app (lib/services/bus_service.dart and journey_planner.dart). Browser-only.
import { getData, getJson, isoDay } from './client';

export type Stop = { id: number; name: string; lat?: number; lon?: number };
export type Dep = { t: number; r: string; d: string; dest: string; trip: number; last: boolean; next?: number };

export const DAY_LABELS: Record<string, string> = {
  'M-F': 'Monday to Friday', 'M-Sa': 'Monday to Saturday', 'M-Th': 'Monday to Thursday', Sa: 'Saturday', Su: 'Sunday',
  SuBh: 'Sundays and bank holidays', Bh: 'Bank holidays', F: 'Fridays', FSa: 'Friday and Saturday', TuTh: 'Tuesday and Thursday',
  MWF: 'Monday, Wednesday, Friday', Sch: 'School days only', Nsch: 'Non-school days only', 'TuTh&Nsch': 'Tuesday and Thursday, non-school days',
};

export type DayCtx = { date: string; weekday: number; bankHoliday: boolean; schoolDay: boolean; label: string };

let termsCache: any = null;
let bhCache: any = null;

export async function dayContext(date = isoDay()): Promise<DayCtx> {
  const d = new Date(date + 'T12:00:00Z');
  const weekday = ((d.getUTCDay() + 6) % 7) + 1; // 1 = Mon .. 7 = Sun
  const isWeekday = weekday <= 5;
  let bankHoliday = false;
  let schoolDay = isWeekday;
  try {
    bhCache ??= await getData('bank_holidays.json');
    bankHoliday = (bhCache.years || []).some((y: any) => (y.holidays || []).some((h: any) => h.date === date));
  } catch {}
  try {
    termsCache ??= await getData('school_terms.json');
    schoolDay = isSchoolDay(date, isWeekday, termsCache) && !bankHoliday;
  } catch {}
  const label = bankHoliday ? 'Bank holiday service' : weekday === 7 ? 'Sunday service' : weekday === 6 ? 'Saturday service' : schoolDay ? 'Weekday (school term)' : 'Weekday (school holidays)';
  return { date, weekday, bankHoliday, schoolDay, label };
}

function isSchoolDay(date: string, isWeekday: boolean, data: any): boolean {
  if (!isWeekday) return false;
  const events = (data.years || []).flatMap((y: any) => (y.terms || []).flatMap((t: any) => t.events || []));
  events.sort((a: any, b: any) => String(a.start).localeCompare(String(b.start)));
  for (const e of events) {
    const off = ['half_term', 'in_service', 'bank_holiday'].includes(e.type);
    if (off && e.start <= date && (e.end || e.start) >= date) return false;
  }
  let open = false;
  for (const e of events) {
    if (e.start > date) break;
    if (e.type === 'term_start') open = true;
    if (e.type === 'term_end') open = false;
  }
  return open;
}

export function matches(pattern: string, c: DayCtx): boolean {
  if (!pattern) return true;
  if (pattern.includes('&')) return pattern.split('&').every((p) => matches(p.trim(), c));
  const w = c.weekday, bh = c.bankHoliday;
  switch (pattern) {
    case 'M-F': return w <= 5 && !bh;
    case 'M-Sa': return w <= 6 && !bh;
    case 'M-Th': return w <= 4 && !bh;
    case 'Sa': return w === 6;
    case 'Su': return w === 7;
    case 'SuBh': return w === 7 || bh;
    case 'Bh': return bh;
    case 'F': return w === 5 && !bh;
    case 'FSa': return (w === 5 || w === 6) && !bh;
    case 'TuTh': return (w === 2 || w === 4) && !bh;
    case 'MWF': return (w === 1 || w === 3 || w === 5) && !bh;
    case 'Sch': return c.schoolDay;
    case 'Nsch': return !c.schoolDay;
    default: return true;
  }
}

export const hm = (m: number) => `${String(Math.floor(m / 60) % 24).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;

export function nowMinutes(): number {
  const t = new Date().toLocaleTimeString('en-GB', { timeZone: 'Europe/London', hour: '2-digit', minute: '2-digit' });
  return Number(t.slice(0, 2)) * 60 + Number(t.slice(3, 5));
}

let stopsCache: Stop[] | null = null;
export async function stops(): Promise<Stop[]> {
  stopsCache ??= ((await getData<any>('bus/stops.json')).stops || []) as Stop[];
  return stopsCache;
}

export async function board(stopId: number): Promise<{ stop: Stop; departures: Dep[] } | null> {
  try {
    return await getData<any>(`bus/stop_${stopId}.json`);
  } catch {
    return null;
  }
}

export function km(lat1: number, lon1: number, lat2: number, lon2: number) {
  const r = 6371, dLat = ((lat2 - lat1) * Math.PI) / 180, dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLon / 2) ** 2;
  return 2 * r * Math.asin(Math.sqrt(Math.min(1, a)));
}

export function searchStops(all: Stop[], q: string, limit = 12): Stop[] {
  const words = q.toLowerCase().split(/[\s,]+/).filter(Boolean);
  if (!words.length) return [];
  return all
    .filter((s) => words.every((w) => s.name.toLowerCase().includes(w)))
    .sort((a, b) => (a.name.toLowerCase().startsWith(words[0]) ? -1 : 0) - (b.name.toLowerCase().startsWith(words[0]) ? -1 : 0) || a.name.localeCompare(b.name))
    .slice(0, limit);
}

export function nearest(all: Stop[], lat: number, lon: number, limit = 8) {
  return all
    .filter((s) => s.lat != null && s.lon != null)
    .map((s) => ({ stop: s, km: km(lat, lon, s.lat!, s.lon!) }))
    .sort((a, b) => a.km - b.km)
    .slice(0, limit);
}

/** Google encoded polyline → [lat, lon][] */
export function decodePolyline(str: string): [number, number][] {
  let index = 0, lat = 0, lng = 0;
  const out: [number, number][] = [];
  while (index < str.length) {
    let b, shift = 0, result = 0;
    do { b = str.charCodeAt(index++) - 63; result |= (b & 0x1f) << shift; shift += 5; } while (b >= 0x20);
    lat += result & 1 ? ~(result >> 1) : result >> 1;
    shift = 0; result = 0;
    do { b = str.charCodeAt(index++) - 63; result |= (b & 0x1f) << shift; shift += 5; } while (b >= 0x20);
    lng += result & 1 ? ~(result >> 1) : result >> 1;
    out.push([lat / 1e5, lng / 1e5]);
  }
  return out;
}

export function routeColour(code: string): string {
  const palette = ['#00695C', '#1565C0', '#C62828', '#6A1B9A', '#EF6C00', '#2E7D32', '#AD1457', '#283593', '#00838F', '#5D4037', '#9E9D24', '#D84315'];
  const n = parseInt(code, 10);
  const i = isNaN(n) ? code.charCodeAt(0) : n;
  return palette[i % palette.length];
}

// ── Journey planner ──
type Trip = { id: number; route: string; days: string; destination: string; stops: number[]; times: number[] };
export type Leg = { kind: 'walk' | 'bus'; fromStop: number; toStop: number; fromName: string; toName: string; depart: number; arrive: number; route?: string; destination?: string; tripId?: number; stopCount?: number; path?: number[] };
export type Journey = { legs: Leg[]; depart: number; arrive: number; changes: number; walk: number; routes: string[] };

let trips: Trip[] | null = null;
let byStop: Map<number, { trip: Trip; index: number }[]> | null = null;
const MIN_TRANSFER = 2, MAX_WAIT = 60, WALK_KMH = 4.8;

export async function loadTrips() {
  if (trips) return;
  const d = await getData<any>('bus/trips.json');
  trips = (d.trips || []).filter((t: any) => Array.isArray(t) && t.length >= 5).map((t: any) => {
    const flat = t[4] as number[];
    const s: number[] = [], tm: number[] = [];
    for (let i = 0; i + 1 < flat.length; i += 2) { s.push(flat[i]); tm.push(flat[i + 1]); }
    return { id: t[0], route: String(t[1]), days: String(t[2]), destination: String(t[3]), stops: s, times: tm };
  });
  byStop = new Map();
  for (const t of trips!) t.stops.forEach((s, i) => { if (!byStop!.has(s)) byStop!.set(s, []); byStop!.get(s)!.push({ trip: t, index: i }); });
}

const journey = (legs: Leg[]): Journey => ({
  legs,
  depart: legs[0].depart,
  arrive: legs[legs.length - 1].arrive,
  changes: Math.max(0, legs.filter((l) => l.kind === 'bus').length - 1),
  walk: legs.filter((l) => l.kind === 'walk').reduce((a, l) => a + l.arrive - l.depart, 0),
  routes: legs.filter((l) => l.kind === 'bus').map((l) => l.route!),
});

function departuresFrom(origin: number, after: number, day: DayCtx) {
  return (byStop!.get(origin) || []).filter((e) => matches(e.trip.days, day) && e.trip.times[e.index] >= after);
}

function busLeg(t: Trip, a: number, b: number, names: Map<number, string>): Leg {
  return { kind: 'bus', fromStop: t.stops[a], toStop: t.stops[b], fromName: names.get(t.stops[a]) || `Stop ${t.stops[a]}`, toName: names.get(t.stops[b]) || `Stop ${t.stops[b]}`, depart: t.times[a], arrive: t.times[b], route: t.route, destination: t.destination, tripId: t.id, stopCount: b - a, path: t.stops.slice(a, b + 1) };
}

export async function plan(origin: number, dest: number, day: DayCtx, after: number, names: Map<number, string>, results = 3): Promise<Journey[]> {
  await loadTrips();
  if (origin === dest) return [];
  const all: Journey[] = [];
  for (const e of departuresFrom(origin, after, day)) {
    const j = e.trip.stops.indexOf(dest, e.index + 1);
    if (j > 0) all.push(journey([busLeg(e.trip, e.index, j, names)]));
  }
  if (all.length < results) {
    // Index trips that reach the destination today: boarding stop → options.
    const reach = new Map<number, { trip: Trip; board: number; destIdx: number }[]>();
    for (const e of byStop!.get(dest) || []) {
      if (!matches(e.trip.days, day)) continue;
      for (let b = 0; b < e.index; b++) {
        const s = e.trip.stops[b];
        if (!reach.has(s)) reach.set(s, []);
        reach.get(s)!.push({ trip: e.trip, board: b, destIdx: e.index });
      }
    }
    for (const e of departuresFrom(origin, after, day)) {
      const a = e.trip;
      for (let x = e.index + 1; x < a.stops.length; x++) {
        for (const o of reach.get(a.stops[x]) || []) {
          if (o.trip.id === a.id) continue;
          const wait = o.trip.times[o.board] - a.times[x];
          if (wait < MIN_TRANSFER || wait > MAX_WAIT) continue;
          all.push(journey([busLeg(a, e.index, x, names), busLeg(o.trip, o.board, o.destIdx, names)]));
        }
      }
    }
  }
  all.sort((a, b) => a.arrive - b.arrive || a.legs.length - b.legs.length || b.depart - a.depart);
  const out: Journey[] = [];
  const seen = new Set<string>();
  for (const j of all) {
    const k = `${j.depart}-${j.arrive}-${j.routes.join(',')}`;
    if (!seen.has(k)) { seen.add(k); out.push(j); }
    if (out.length >= results) break;
  }
  return out;
}

export type Place = { label: string; lat: number; lon: number; stopId?: number };

export function stopsNear(all: Stop[], lat: number, lon: number, maxKm = 1, limit = 3) {
  return nearest(all, lat, lon, 30)
    .filter((x) => x.km <= maxKm)
    .slice(0, limit)
    .map((x) => ({ stop: x.stop, walk: Math.max(1, Math.round((x.km / WALK_KMH) * 60)) }));
}

export async function planPlaces(from: Place, to: Place, day: DayCtx, after: number, all: Stop[], results = 4): Promise<Journey[]> {
  const names = new Map(all.map((s) => [s.id, s.name]));
  // A chosen stop also counts the stops a short walk away, so a direct bus to
  // the next stop along beats a change of bus.
  const around = (p: Place) => {
    if (!p.stopId) return stopsNear(all, p.lat, p.lon);
    const self = all.find((s) => s.id === p.stopId)!;
    const near = self?.lat != null ? stopsNear(all, self.lat, self.lon!, 0.4, 4).filter((x) => x.stop.id !== p.stopId) : [];
    return [{ stop: self, walk: 0 }, ...near];
  };
  const fromStops = around(from);
  const toStops = around(to);
  const out: Journey[] = [];
  for (const f of fromStops) {
    for (const t of toStops) {
      if (f.stop.id === t.stop.id) continue;
      for (const j of await plan(f.stop.id, t.stop.id, day, after + f.walk, names, 2)) {
        const legs: Leg[] = [];
        if (f.walk > 0) legs.push({ kind: 'walk', fromStop: -1, toStop: f.stop.id, fromName: from.label, toName: f.stop.name, depart: j.depart - f.walk, arrive: j.depart });
        legs.push(...j.legs);
        if (t.walk > 0) legs.push({ kind: 'walk', fromStop: t.stop.id, toStop: -2, fromName: t.stop.name, toName: to.label, depart: j.arrive, arrive: j.arrive + t.walk });
        out.push(journey(legs));
      }
    }
  }
  out.sort((a, b) => a.arrive - b.arrive || a.changes - b.changes || a.walk - b.walk);
  const seen = new Set<string>();
  return out.filter((j) => { const k = `${j.arrive}-${j.routes.join(',')}`; if (seen.has(k)) return false; seen.add(k); return true; }).slice(0, results);
}

export async function searchPlaces(q: string): Promise<Place[]> {
  if (q.trim().length < 2) return [];
  try {
    const d = await getJson<any>(`https://manxone-places.hammerpunch786.workers.dev/?q=${encodeURIComponent(q.trim())}`, 10000);
    return (d.results || []).filter((p: any) => p.lat && p.lon).map((p: any) => ({ label: p.label || p.full, lat: p.lat, lon: p.lon }));
  } catch {
    return [];
  }
}

export async function liveVehicles(): Promise<{ updated: string; vehicles: any[] }> {
  const d = await getJson<any>('https://manxone-live.hammerpunch786.workers.dev/', 12000);
  return { updated: d.updated || '', vehicles: d.vehicles || [] };
}
