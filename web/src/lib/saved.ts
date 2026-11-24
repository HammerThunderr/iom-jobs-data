// Saved jobs, kept in this browser.
import { store } from './client';

export type Saved = { kind: 'job' | 'gov'; id: string; title: string; sub: string; href: string; at?: number };

export function savedList(): Saved[] {
  return store.get<Saved[]>('saved', []);
}

export function isSaved(kind: string, id: string) {
  return savedList().some((s) => s.kind === kind && s.id === id);
}

export function toggleSaved(item: Saved): boolean {
  const list = savedList();
  const i = list.findIndex((s) => s.kind === item.kind && s.id === item.id);
  if (i >= 0) list.splice(i, 1);
  else list.unshift({ ...item, at: Date.now() });
  store.set('saved', list);
  return i < 0;
}

/** Wire every [data-save] button on the page. */
export function wireSaveButtons(root: ParentNode = document) {
  root.querySelectorAll<HTMLButtonElement>('[data-save]').forEach((b) => {
    if (b.dataset.wired) return;
    b.dataset.wired = '1';
    const item = JSON.parse(b.dataset.save!) as Saved;
    const paint = (on: boolean) => {
      b.setAttribute('aria-pressed', String(on));
      b.title = on ? 'Saved' : 'Save';
    };
    paint(isSaved(item.kind, item.id));
    b.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      paint(toggleSaved(item));
    });
  });
}
