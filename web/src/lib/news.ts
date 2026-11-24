import { remote } from './data';

export const NEWS_URL = 'https://raw.githubusercontent.com/HammerThunderr/IOM_OPEN_DATA/main/data/news.json';

export type NewsItem = { title: string; link: string; published: string; summary: string; source: string; image: string };

export const NEWS_COLOURS: Record<string, string> = {
  'Manx Radio': '#C62828',
  'Three FM': '#1565C0',
  'Energy FM': '#EF6C00',
  'Isle of Man Government': '#2E7D32',
  'Google News': '#455A64',
};

export async function news(): Promise<{ items: NewsItem[]; generated: string }> {
  const d = await remote<any>(NEWS_URL);
  const items: NewsItem[] = (d?.items ?? [])
    .filter((n: any) => n && n.title && /^https?:/.test(n.link || ''))
    .map((n: any) => ({ ...n, image: /^https?:/.test(n.image || '') ? n.image : '' }))
    .sort((a: NewsItem, b: NewsItem) => String(b.published).localeCompare(String(a.published)));
  return { items, generated: d?.generated_at ?? '' };
}
