// Category colours and icons (safe to import in the browser).
export const EVENT_STYLE: Record<string, { color: string; icon: string }> = {
  Festive: { color: '#C62828', icon: 'celebration' },
  'Family & Kids': { color: '#EF6C00', icon: 'child_care' },
  Music: { color: '#6A1B9A', icon: 'music_note' },
  'Theatre & Comedy': { color: '#AD1457', icon: 'theater_comedy' },
  Film: { color: '#283593', icon: 'movie' },
  'Arts & Workshops': { color: '#00838F', icon: 'palette' },
  Heritage: { color: '#5D4037', icon: 'castle' },
  'Talks & Learning': { color: '#455A64', icon: 'record_voice_over' },
  Sport: { color: '#2E7D32', icon: 'sports' },
  'Markets & Fairs': { color: '#9E9D24', icon: 'storefront' },
  Community: { color: '#00695C', icon: 'groups' },
  Other: { color: '#546E7A', icon: 'event' },
};

export function styleFor(c: string) {
  return EVENT_STYLE[c] ?? EVENT_STYLE.Other;
}

/*icons*/ ['celebration', 'child_care', 'music_note', 'theater_comedy', 'movie', 'palette', 'castle', 'record_voice_over', 'sports', 'storefront', 'groups', 'event'];
