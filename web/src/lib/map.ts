// Leaflet with OpenStreetMap tiles. Browser-only.
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

export { L };

export const IOM_CENTER: [number, number] = [54.236, -4.548];

export function createMap(el: HTMLElement, center: [number, number] = IOM_CENTER, zoom = 10) {
  const map = L.map(el, { scrollWheelZoom: false, zoomControl: true }).setView(center, zoom);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map);
  // Let people scroll the page past the map; zoom with ctrl/cmd + wheel.
  el.addEventListener('wheel', (e) => {
    if (e.ctrlKey || e.metaKey) map.scrollWheelZoom.enable();
    else map.scrollWheelZoom.disable();
  });
  return map;
}

export function dotIcon(color: string, label = '', size = 26) {
  return L.divIcon({
    className: 'mx-dot',
    html: `<span style="background:${color};width:${size}px;height:${size}px">${label}</span>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

export function arrowIcon(color: string, deg: number | null, size = 28, glyph = 'navigation') {
  return L.divIcon({
    className: 'mx-arrow',
    html: `<span class="ms" style="color:${color};font-size:${size}px;transform:rotate(${deg ?? 0}deg)">${deg == null ? 'circle' : glyph}</span>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

/*icons*/ ['navigation', 'circle', 'flight', 'directions_bus'];
