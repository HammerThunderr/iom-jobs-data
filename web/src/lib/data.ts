// Build-time data access. Pages read the same JSON feeds the app uses.
// DATA_DIR defaults to ../docs (the iom-jobs-data GitHub Pages folder), so a
// build inside this repo always uses the newest committed data.
import fs from 'node:fs';
import path from 'node:path';

const DIR = path.resolve(process.env.DATA_DIR || '../docs');
const cache = new Map<string, any>();

export function load<T = any>(name: string): T | null {
  if (cache.has(name)) return cache.get(name);
  let value: any = null;
  try {
    value = JSON.parse(fs.readFileSync(path.join(DIR, name), 'utf8'));
  } catch (e) {
    console.warn(`data: could not read ${name}: ${(e as Error).message}`);
  }
  cache.set(name, value);
  return value;
}

/** JSON from another public repo (news, Tynwald). Returns null on failure. */
export async function remote<T = any>(url: string): Promise<T | null> {
  if (cache.has(url)) return cache.get(url);
  let value: any = null;
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 20000);
    const res = await fetch(url, { signal: ctrl.signal });
    clearTimeout(t);
    if (res.ok) value = await res.json();
  } catch (e) {
    console.warn(`data: could not fetch ${url}: ${(e as Error).message}`);
  }
  cache.set(url, value);
  return value;
}

export type Features = Record<string, { enabled: boolean; message?: string }>;

export function features(): Features {
  return load<any>('features.json')?.features ?? {};
}

export function featureOff(key: string): string | null {
  const f = features()[key];
  if (f && f.enabled === false) return f.message || 'This section is temporarily unavailable.';
  return null;
}
