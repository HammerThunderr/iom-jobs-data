// Duty pharmacy rota helpers (build + browser).
export type RotaEntry = { date: string; pharmacy: { name: string; address: string; phone: string; hours: string } | null; note: string };
export type Area = { key: string; name: string; entries: RotaEntry[] };

export const phoneDisplay = (p: string) => String(p || '').replace(/^\+44/, '0').replace(/^(0\d{4})(\d{6})$/, '$1 $2');
export const tel = (p: string) => 'tel:' + String(p || '').replace(/[^\d+]/g, '');

export function rotaHtml(areas: Area[], from: string, to: string): string {
  const esc = (s: unknown) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]!));
  const dates = [...new Set(areas.flatMap((a) => a.entries.map((e) => e.date)))].filter((d) => d >= from && d <= to).sort();
  if (!dates.length) return '<div class="card empty"><p>No duty dates in this period.</p></div>';
  return dates
    .map((d) => {
      const label = new Date(d + 'T12:00:00Z').toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' });
      const note = areas.flatMap((a) => a.entries.filter((e) => e.date === d && e.note)).map((e) => e.note)[0] || '';
      const rows = areas
        .filter((a) => a.entries.length)
        .map((a) => {
          const e = a.entries.find((x) => x.date === d);
          if (!e) return '';
          return e.pharmacy
            ? `<a href="${tel(e.pharmacy.phone)}"><span class="grow"><span class="tiny muted">${esc(a.name)}</span><br><strong>${esc(e.pharmacy.name)}</strong><br><span class="small muted">${esc(e.pharmacy.address)}</span></span><span class="small" style="text-align:right"><strong>${esc(e.pharmacy.hours)}</strong><br>${esc(phoneDisplay(e.pharmacy.phone))}</span></a>`
            : `<div><span class="grow"><span class="tiny muted">${esc(a.name)}</span><br><span class="muted">${esc(e.note || 'No pharmacy on duty')}</span></span></div>`;
        })
        .join('');
      return `<section class="section" data-date="${d}"><h3>${label}${note ? ` <span class="tag warn">${esc(note.replace(/\s*—.*$/, ''))}</span>` : ''}</h3><div class="rows">${rows}</div></section>`;
    })
    .join('');
}
