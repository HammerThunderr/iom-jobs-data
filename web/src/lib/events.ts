import { load } from './data';
import { isoDay, slugify } from './format';

export type Occ = { date: string; time: string; soldOut: boolean };
export type Ev = {
  id: string;
  slug: string;
  title: string;
  venue: string;
  area: string;
  address: string;
  category: string;
  tags: string[];
  start: string;
  end: string;
  time: string;
  price: string;
  description: string;
  image: string;
  url: string;
  bookingUrl: string;
  source: string;
  soldOut: boolean;
  occurrences: Occ[];
  alsoListedOn: string[];
};

import { EVENT_STYLE, styleFor } from './event-style';
export { EVENT_STYLE, styleFor };

const bool = (v: unknown) => v === true || v === 'true' || v === 'True';

let cache: Ev[] | null = null;
export function events(): Ev[] {
  if (cache) return cache;
  const raw = load<any>('events.json')?.events ?? [];
  const used = new Set<string>();
  cache = raw.map((e: any): Ev => {
    const tags = Array.isArray(e.tags) ? e.tags.map(String) : [];
    let slug = slugify(e.title) || 'event';
    if (used.has(slug)) slug = `${slug}-${slugify(e.id || e.startDate)}`;
    while (used.has(slug)) slug += '-x';
    used.add(slug);
    return {
      id: e.id || slug,
      slug,
      title: e.title || '',
      venue: e.venue || '',
      area: e.area || '',
      address: e.address || '',
      category: e.category || tags[0] || 'Other',
      tags,
      start: e.startDate || '',
      end: e.endDate || e.startDate || '',
      time: e.time || '',
      price: e.price || '',
      description: e.description || '',
      image: /^https?:/.test(e.imageUrl || '') ? e.imageUrl : '',
      url: e.url || '',
      bookingUrl: e.bookingUrl || '',
      source: e.source || '',
      soldOut: bool(e.soldOut),
      occurrences: Array.isArray(e.occurrences) ? e.occurrences.map((o: any) => ({ date: String(o.date || ''), time: String(o.time || ''), soldOut: bool(o.soldOut) })) : [],
      alsoListedOn: Array.isArray(e.alsoListedOn) ? e.alsoListedOn : [],
    };
  });
  return cache!;
}

/** Every day this event runs, as YYYY-MM-DD (capped for long runs). */
export function days(e: Ev): string[] {
  if (e.occurrences.length) return [...new Set(e.occurrences.map((o) => o.date).filter(Boolean))].sort();
  if (!e.start) return [];
  return [e.start];
}

export function isLongRun(e: Ev) {
  if (e.occurrences.length || !e.start || !e.end) return false;
  return (Date.parse(e.end) - Date.parse(e.start)) / 86400000 >= 3;
}

/** Next date on or after today (as of the build). */
export function nextDate(e: Ev, today = isoDay()): string | null {
  if (e.occurrences.length) return days(e).find((d) => d >= today) ?? null;
  if (!e.start) return null;
  if (e.end && e.end < today) return null;
  return e.start < today ? today : e.start;
}

export function upcoming(today = isoDay()): Ev[] {
  return events()
    .filter((e) => nextDate(e, today))
    .sort((a, b) => nextDate(a, today)!.localeCompare(nextDate(b, today)!) || a.title.localeCompare(b.title));
}

export function dateLabel(e: Ev): string {
  const f = (s: string, o: Intl.DateTimeFormatOptions) => new Date(s + 'T12:00:00Z').toLocaleDateString('en-GB', o);
  const d = days(e);
  if (isLongRun(e)) return `${f(e.start, { day: 'numeric', month: 'short' })} – ${f(e.end, { day: 'numeric', month: 'short', year: 'numeric' })}`;
  if (d.length > 1) return `${f(d[0], { weekday: 'short', day: 'numeric', month: 'short' })} – ${f(d[d.length - 1], { day: 'numeric', month: 'short' })} · ${d.length} dates`;
  if (e.start && e.end && e.end !== e.start) return `${f(e.start, { weekday: 'short', day: 'numeric', month: 'short' })} – ${f(e.end, { weekday: 'short', day: 'numeric', month: 'short' })}`;
  return e.start ? f(e.start, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }) : 'Date to be confirmed';
}

