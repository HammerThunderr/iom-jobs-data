import type { APIRoute } from 'astro';

// Every built page, from Astro's own page list.
const pages = import.meta.glob('./**/*.astro');
import { jobs, govJobs } from '../lib/jobs';
import { events } from '../lib/events';
import { load } from '../lib/data';

export const GET: APIRoute = ({ site }) => {
  const statics = Object.keys(pages)
    .map((p) => p.replace(/^\.\//, '/').replace(/index\.astro$/, '').replace(/\.astro$/, '/'))
    .filter((p) => !p.includes('[') && !/\/(404|bookmarks|events\/(my|review|community|submit))\/?$/.test(p));
  const urls = [
    ...statics,
    ...jobs().map((j) => `/jobs/${j.slug}/`),
    ...govJobs().map((j) => `/gov-jobs/${j.slug}/`),
    ...events().map((e) => `/events/${e.slug}/`),
    ...(load<any>('bus/index.json')?.routes ?? []).map((r: any) => `/bus/route/${r.code}/`),
  ];
  const today = new Date().toISOString().slice(0, 10);
  const body = `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls
    .map((u) => `  <url><loc>${new URL(u, site)}</loc><lastmod>${today}</lastmod></url>`)
    .join('\n')}\n</urlset>\n`;
  return new Response(body, { headers: { 'Content-Type': 'application/xml' } });
};
