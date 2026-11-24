// Browser helpers shared by page scripts.
// Live data comes straight from the data repo's GitHub Pages site so pages
// stay fresh between site builds; the copy bundled with the site is the
// fallback.
const LIVE = 'https://hammerthunderr.github.io/iom-jobs-data/';

export async function getData<T = any>(name: string, opts: { live?: boolean } = { live: true }): Promise<T> {
  if (opts.live !== false) {
    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 8000);
      const r = await fetch(LIVE + name, { cache: 'no-cache', signal: ctrl.signal });
      clearTimeout(t);
      if (r.ok) return await r.json();
    } catch {}
  }
  const r = await fetch('/data/' + name);
  if (!r.ok) throw new Error(`${name}: ${r.status}`);
  return r.json();
}

export async function getJson<T = any>(url: string, timeoutMs = 10000): Promise<T> {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const r = await fetch(url, { signal: ctrl.signal });
    if (!r.ok) throw new Error(`${r.status}`);
    return await r.json();
  } finally {
    clearTimeout(t);
  }
}

export const TZ = 'Europe/London';

export function esc(s: unknown): string {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]!));
}

export function fmtTime(v: unknown): string {
  const d = v instanceof Date ? v : new Date(String(v));
  return isNaN(d.getTime()) ? '' : d.toLocaleTimeString('en-GB', { timeZone: TZ, hour: '2-digit', minute: '2-digit' });
}

export function fmtDay(v: unknown): string {
  const d = v instanceof Date ? v : new Date(String(v));
  return isNaN(d.getTime()) ? '' : d.toLocaleDateString('en-GB', { timeZone: TZ, weekday: 'short', day: 'numeric', month: 'short' });
}

export function isoDay(d: Date = new Date()): string {
  return d.toLocaleDateString('en-CA', { timeZone: TZ });
}

export function ago(v: unknown): string {
  const d = v instanceof Date ? v : new Date(String(v));
  if (isNaN(d.getTime())) return '';
  const m = Math.round((Date.now() - d.getTime()) / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} hr ago`;
  const days = Math.round(h / 24);
  return `${days} day${days === 1 ? '' : 's'} ago`;
}

/** Small localStorage wrapper that never throws. */
export const store = {
  get<T>(key: string, fallback: T): T {
    try {
      const v = localStorage.getItem('mx:' + key);
      return v == null ? fallback : JSON.parse(v);
    } catch {
      return fallback;
    }
  },
  set(key: string, value: unknown) {
    try {
      localStorage.setItem('mx:' + key, JSON.stringify(value));
    } catch {}
  },
};

export function $(sel: string, root: ParentNode = document) {
  return root.querySelector(sel) as HTMLElement | null;
}

export function $$(sel: string, root: ParentNode = document) {
  return Array.from(root.querySelectorAll(sel)) as HTMLElement[];
}

/** Wire a text box + chip filters to a list of [data-search] items. */
export function wireFilter(opts: {
  input?: HTMLInputElement | null;
  items: HTMLElement[];
  chips?: HTMLElement[];
  chipAttr?: string;
  count?: HTMLElement | null;
  empty?: HTMLElement | null;
}) {
  let chip = 'all';
  const run = () => {
    const q = (opts.input?.value || '').trim().toLowerCase();
    const words = q.split(/\s+/).filter(Boolean);
    let shown = 0;
    for (const el of opts.items) {
      const hay = (el.dataset.search || el.textContent || '').toLowerCase();
      const okText = words.every((w) => hay.includes(w));
      const val = opts.chipAttr ? (el.getAttribute(opts.chipAttr) || '') : '';
      const okChip = chip === 'all' || val.split('|').includes(chip);
      const show = okText && okChip;
      el.hidden = !show;
      if (show) shown++;
    }
    if (opts.count) opts.count.textContent = String(shown);
    if (opts.empty) opts.empty.hidden = shown > 0;
  };
  opts.input?.addEventListener('input', run);
  for (const c of opts.chips || []) {
    c.addEventListener('click', () => {
      chip = c.dataset.value || 'all';
      for (const o of opts.chips!) o.setAttribute('aria-pressed', String(o === c));
      run();
    });
  }
  run();
  return run;
}

/** Icon markup for scripts. Keep names as literals: scripts/icons.mjs reads them. */
export function ic(name: string, cls = ''): string {
  return `<span class="ms ${cls}" aria-hidden="true">${name}</span>`;
}
/*icons*/ ['trending_up', 'trending_down'];
