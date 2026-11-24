// Pure HTML renderers shared by the build and the browser.
import type { Flight, FerryDay } from './live';

const esc = (s: unknown) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]!));
const cls = (t: string) => ({ cancelled: 'bad', delayed: 'warn', departed: 'info', arrived: 'ok', boarding: 'warn', ontime: 'ok' } as Record<string, string>)[t] ?? '';

export function ferryHtml(days: FerryDay[], todayIso: string): string {
  if (!days.length) return '<div class="card empty"><p>No sailings listed right now.</p></div>';
  return days
    .map((d) => {
      const label = d.iso === todayIso ? `Today · ${d.date}` : d.date;
      const rows = d.sailings
        .map(
          (s) => `<tr><td><strong>${esc(s.departTime)}</strong> ${esc(s.departPort)}</td><td><span class="ms" aria-hidden="true">arrow_forward</span></td><td><strong>${esc(s.arriveTime)}</strong> ${esc(s.arrivePort)}</td><td class="hide-sm">${esc(s.ferry)}</td><td>${s.status ? `<span class="tag ${cls(s.statusType)}">${esc(s.status)}</span>` : ''}</td></tr>`,
        )
        .join('');
      return `<section class="section"><h2>${esc(label)}</h2><div class="table-wrap"><table class="table"><thead><tr><th>Departs</th><th></th><th>Arrives</th><th class="hide-sm">Vessel</th><th>Status</th></tr></thead><tbody>${rows}</tbody></table></div></section>`;
    })
    .join('');
}

export function flightsHtml(list: Flight[], dep: boolean): string {
  if (!list.length) return '<div class="card empty"><p>No flights listed right now.</p></div>';
  const rows = list
    .map(
      (f) => `<tr><td class="nowrap"><strong>${esc(f.scheduled)}</strong></td><td>${esc(f.place)}</td><td class="nowrap">${esc(f.flightNo)}<div class="tiny muted">${esc(f.airline)}</div></td><td>${f.status ? `<span class="tag ${cls(f.statusType)}">${esc(f.status)}</span>` : ''}</td></tr>`,
    )
    .join('');
  return `<div class="table-wrap"><table class="table"><thead><tr><th>Time</th><th>${dep ? 'To' : 'From'}</th><th>Flight</th><th>Status</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}
