// Shared weather helpers (build + browser).

/** Splits the gov.im "##Heading##\n\ntext" feed format into sections. */
export function govSections(desc: string): { heading: string; text: string }[] {
  const out: { heading: string; text: string }[] = [];
  const parts = String(desc || '').split(/##([^#]+)##/);
  for (let i = 1; i < parts.length; i += 2) {
    out.push({ heading: parts[i].trim().replace(/:$/, ''), text: (parts[i + 1] || '').trim() });
  }
  return out;
}

/** The 5-day feed repeats Temperature/Wind/... after each day heading. */
export function govDays(desc: string) {
  const secs = govSections(desc);
  const days: { day: string; summary: string; fields: Record<string, string> }[] = [];
  for (const s of secs) {
    const isField = /^(Temperature|Rainfall|Wind Speed|Wind Direction|Wind|Visibility|Comments)/i.test(s.heading);
    if (!isField) days.push({ day: s.heading, summary: s.text, fields: {} });
    else if (days.length) days[days.length - 1].fields[s.heading.replace(/\s*\(mm\)/i, '')] = s.text;
  }
  return days;
}

export const WMO: Record<number, [string, string, string]> = {
  // code: [label, day icon, night icon]
  0: ['Clear sky', 'clear_day', 'bedtime'],
  1: ['Mainly clear', 'partly_cloudy_day', 'partly_cloudy_night'],
  2: ['Partly cloudy', 'partly_cloudy_day', 'partly_cloudy_night'],
  3: ['Overcast', 'cloud', 'cloud'],
  45: ['Fog', 'foggy', 'foggy'],
  48: ['Freezing fog', 'foggy', 'foggy'],
  51: ['Light drizzle', 'rainy_light', 'rainy_light'],
  53: ['Drizzle', 'rainy_light', 'rainy_light'],
  55: ['Heavy drizzle', 'rainy', 'rainy'],
  56: ['Freezing drizzle', 'weather_mix', 'weather_mix'],
  57: ['Freezing drizzle', 'weather_mix', 'weather_mix'],
  61: ['Light rain', 'rainy_light', 'rainy_light'],
  63: ['Rain', 'rainy', 'rainy'],
  65: ['Heavy rain', 'rainy_heavy', 'rainy_heavy'],
  66: ['Freezing rain', 'weather_mix', 'weather_mix'],
  67: ['Freezing rain', 'weather_mix', 'weather_mix'],
  71: ['Light snow', 'weather_snowy', 'weather_snowy'],
  73: ['Snow', 'weather_snowy', 'weather_snowy'],
  75: ['Heavy snow', 'snowing_heavy', 'snowing_heavy'],
  77: ['Snow grains', 'weather_snowy', 'weather_snowy'],
  80: ['Light showers', 'rainy_light', 'rainy_light'],
  81: ['Showers', 'rainy', 'rainy'],
  82: ['Heavy showers', 'rainy_heavy', 'rainy_heavy'],
  85: ['Snow showers', 'weather_snowy', 'weather_snowy'],
  86: ['Heavy snow showers', 'snowing_heavy', 'snowing_heavy'],
  95: ['Thunderstorm', 'thunderstorm', 'thunderstorm'],
  96: ['Thunderstorm, hail', 'thunderstorm', 'thunderstorm'],
  99: ['Thunderstorm, hail', 'thunderstorm', 'thunderstorm'],
};

export function wmo(code: number, isDay = true): { label: string; icon: string } {
  const w = WMO[code] ?? ['Unknown', 'cloud', 'cloud'];
  return { label: w[0], icon: isDay ? w[1] : w[2] };
}

export function compass(deg: number): string {
  const d = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'];
  return d[Math.round((((deg % 360) + 360) % 360) / 22.5) % 16];
}

export const LOCATIONS = [
  { name: 'Douglas', lat: 54.152, lon: -4.486 },
  { name: 'Onchan', lat: 54.176, lon: -4.457 },
  { name: 'Ramsey', lat: 54.323, lon: -4.386 },
  { name: 'Peel', lat: 54.226, lon: -4.694 },
  { name: 'Castletown', lat: 54.074, lon: -4.652 },
  { name: 'Port Erin', lat: 54.085, lon: -4.749 },
  { name: 'Laxey', lat: 54.226, lon: -4.398 },
  { name: 'Ronaldsway Airport', lat: 54.083, lon: -4.624 },
  { name: 'Snaefell Summit', lat: 54.264, lon: -4.464 },
];

export const SEA_AREAS = [
  { name: 'East coast', desc: 'Douglas, Onchan, Laxey', lat: 54.15, lon: -4.25 },
  { name: 'West coast', desc: 'Peel, Kirk Michael', lat: 54.23, lon: -4.9 },
  { name: 'North', desc: 'Ramsey, Point of Ayre', lat: 54.45, lon: -4.35 },
  { name: 'South', desc: 'Castletown, Port Erin, Calf of Man', lat: 53.98, lon: -4.7 },
];

/** Beaufort description for a wind speed in mph. */
export function beaufort(mph: number): string {
  const t: [number, string][] = [
    [1, 'Calm'], [4, 'Light air'], [8, 'Light breeze'], [13, 'Gentle breeze'], [19, 'Moderate breeze'],
    [25, 'Fresh breeze'], [32, 'Strong breeze'], [39, 'Near gale'], [47, 'Gale'], [55, 'Strong gale'],
    [64, 'Storm'], [73, 'Violent storm'],
  ];
  for (const [max, label] of t) if (mph < max) return label;
  return 'Hurricane force';
}

// Icon names used above, for the icon-font subset (scripts/icons.mjs):
/*icons*/ ['clear_day', 'bedtime', 'partly_cloudy_day', 'partly_cloudy_night', 'cloud', 'foggy', 'rainy_light', 'rainy', 'rainy_heavy', 'weather_mix', 'weather_snowy', 'snowing_heavy', 'thunderstorm'];
