// Shared formatting helpers. Everything is shown in Isle of Man time.
export const TZ = 'Europe/London';

export function toDate(v: unknown): Date | null {
  if (!v) return null;
  const d = v instanceof Date ? v : new Date(String(v));
  return isNaN(d.getTime()) ? null : d;
}

export function fmtDate(v: unknown, opts: Intl.DateTimeFormatOptions = { day: 'numeric', month: 'short', year: 'numeric' }): string {
  const d = toDate(v);
  return d ? d.toLocaleDateString('en-GB', { timeZone: TZ, ...opts }) : '';
}

export function fmtDay(v: unknown): string {
  return fmtDate(v, { weekday: 'short', day: 'numeric', month: 'short' });
}

export function fmtLongDay(v: unknown): string {
  return fmtDate(v, { weekday: 'long', day: 'numeric', month: 'long' });
}

export function fmtTime(v: unknown): string {
  const d = toDate(v);
  return d ? d.toLocaleTimeString('en-GB', { timeZone: TZ, hour: '2-digit', minute: '2-digit' }) : '';
}

export function fmtDateTime(v: unknown): string {
  const d = toDate(v);
  return d ? `${fmtDate(d)}, ${fmtTime(d)}` : '';
}

/** "YYYY-MM-DD" for a date in Isle of Man time. */
export function isoDay(v: unknown = new Date()): string {
  const d = toDate(v) ?? new Date();
  return d.toLocaleDateString('en-CA', { timeZone: TZ });
}

export function slugify(s: string): string {
  return String(s || '')
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/&/g, ' and ')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 80);
}

export function plain(html: string): string {
  return String(html || '')
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<\/(p|div|li|h\d)>/gi, '\n')
    .replace(/<[^>]+>/g, '')
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;|&#039;|&rsquo;|&lsquo;/g, "'")
    .replace(/&pound;/g, '£')
    .replace(/[ \t]+/g, ' ')
    .replace(/\n\s*\n\s*\n+/g, '\n\n')
    .trim();
}

export function excerpt(s: string, n = 180): string {
  const t = plain(s).replace(/\s+/g, ' ');
  return t.length > n ? t.slice(0, n).replace(/\s+\S*$/, '') + '…' : t;
}

export function money(n: number | null | undefined): string {
  if (n == null) return '';
  return '£' + Math.round(n).toLocaleString('en-GB');
}

export function telHref(p: string): string {
  return 'tel:' + String(p || '').replace(/[^\d+]/g, '');
}

export function mapsHref(q: string): string {
  return 'https://www.google.com/maps/search/?api=1&query=' + encodeURIComponent(q);
}

export function safeUrl(u: unknown): string | null {
  const s = String(u || '').trim();
  return /^https?:\/\//i.test(s) ? s : null;
}

export function escHtml(s: string): string {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]!));
}

/** Escaped text with paragraphs, bullet lines, links and emails. */
export function richText(text: string): string {
  const linkify = (t: string) =>
    escHtml(t)
      .replace(/\bhttps?:\/\/[^\s<]+[^\s<.,;:)]/g, (u) => `<a href="${u}" target="_blank" rel="noopener nofollow">${u}</a>`)
      .replace(/(?<![\/\w.>])(www\.[a-z0-9.-]+\.[a-z]{2,}[^\s<]*[^\s<.,;:)])/gi, (u) => `<a href="https://${u}" target="_blank" rel="noopener nofollow">${u}</a>`)
      .replace(/\b[\w.+-]+@[\w-]+(\.[\w-]+)+\b/g, (e) => `<a href="mailto:${e}">${e}</a>`);
  const blocks = String(text || '').trim().split(/\n\s*\n/);
  return blocks
    .map((b) => {
      const lines = b.split('\n').map((l) => l.trim()).filter(Boolean);
      if (lines.length > 1 && lines.every((l) => /^[•\-*·]/.test(l))) {
        return '<ul>' + lines.map((l) => `<li>${linkify(l.replace(/^[•\-*·]\s*/, ''))}</li>`).join('') + '</ul>';
      }
      return lines
        .map((l) => (/^[•\-*·]\s/.test(l) ? `<p class="bullet">${linkify(l)}</p>` : l.length < 70 && /:$/.test(l) ? `<h3>${linkify(l)}</h3>` : `<p>${linkify(l)}</p>`))
        .join('');
    })
    .join('');
}
