// Every section of the site, mirroring the app's home screen.
export type Section = {
  key: string; // features.json key where one exists
  title: string;
  subtitle: string;
  icon: string; // Material Symbols name
  color: string;
  href: string;
  group: 'live' | 'work' | 'travel' | 'out' | 'info';
};

export const GROUPS: Record<Section['group'], string> = {
  live: 'Live & local',
  work: 'Work & home',
  travel: 'Getting around',
  out: 'Out & about',
  info: 'Useful info',
};

export function christmasInSeason(d = new Date()): boolean {
  const m = d.getMonth() + 1;
  const day = d.getDate();
  return (m === 11 && day >= 15) || m === 12 || (m === 1 && day <= 6);
}

const ALL: Section[] = [
  { key: 'christmas', title: 'Christmas', subtitle: 'Festive guide', icon: 'celebration', color: '#B71C1C', href: '/christmas/', group: 'out' },
  { key: 'news', title: 'News', subtitle: 'Latest headlines', icon: 'newspaper', color: '#673AB7', href: '/news/', group: 'live' },
  { key: 'weather', title: 'Weather', subtitle: 'Forecast', icon: 'cloud', color: '#0288D1', href: '/weather/', group: 'live' },
  { key: 'webcams', title: 'Webcams', subtitle: 'Live cameras', icon: 'videocam', color: '#2E7D32', href: '/webcams/', group: 'live' },
  { key: 'radio', title: 'Radio', subtitle: 'IOM stations', icon: 'radio', color: '#8E24AA', href: '/radio/', group: 'live' },
  { key: 'road_signs', title: 'Road Signs', subtitle: 'Live matrix signs', icon: 'signpost', color: '#EF6C00', href: '/road-signs/', group: 'live' },
  { key: 'road_closures', title: 'Road Closures', subtitle: 'Roadworks & events', icon: 'remove_road', color: '#C62828', href: '/road-closures/', group: 'live' },

  { key: 'jobs', title: 'Jobs', subtitle: 'Vacancies', icon: 'work', color: '#1E88E5', href: '/jobs/', group: 'work' },
  { key: 'govJobs', title: 'Gov Jobs', subtitle: 'JobTrain', icon: 'account_balance', color: '#3949AB', href: '/gov-jobs/', group: 'work' },
  { key: 'property', title: 'Property', subtitle: 'Buy & rent', icon: 'home_work', color: '#6D4C41', href: '/property/', group: 'work' },
  { key: 'bins', title: 'Bin Day', subtitle: 'Collections & recycling', icon: 'delete', color: '#827717', href: '/bins/', group: 'work' },
  { key: 'volunteer', title: 'Volunteer', subtitle: 'Give back', icon: 'volunteer_activism', color: '#43A047', href: '/volunteer/', group: 'work' },
  { key: 'farming', title: 'Farming', subtitle: 'Exports, grants & more', icon: 'agriculture', color: '#558B2F', href: '/farming/', group: 'work' },
  { key: 'bookmarks', title: 'Bookmarks', subtitle: 'Saved jobs', icon: 'bookmark', color: '#00897B', href: '/bookmarks/', group: 'work' },

  { key: 'bus_times', title: 'Bus', subtitle: 'Times, map & tracker', icon: 'directions_bus', color: '#00695C', href: '/bus/', group: 'travel' },
  { key: 'ferry', title: 'Ferry', subtitle: 'Sailings', icon: 'directions_boat', color: '#3949AB', href: '/ferry/', group: 'travel' },
  { key: 'flights', title: 'Flights', subtitle: 'Live status', icon: 'flight_takeoff', color: '#0097A7', href: '/flights/', group: 'travel' },
  { key: 'railways', title: 'Trams & Rail', subtitle: 'Heritage timetables', icon: 'tram', color: '#FF8F00', href: '/railways/', group: 'travel' },
  { key: 'cruise', title: 'Cruise Ships', subtitle: "Who's in port", icon: 'sailing', color: '#1976D2', href: '/cruise/', group: 'travel' },
  { key: 'tides', title: 'Tides', subtitle: 'High & low water', icon: 'waves', color: '#00838F', href: '/tides/', group: 'travel' },
  { key: 'driving', title: 'Learn to Drive', subtitle: 'Instructors & tests', icon: 'directions_car', color: '#546E7A', href: '/driving/', group: 'travel' },

  { key: 'events', title: "What's On", subtitle: 'Events', icon: 'event', color: '#5E35B1', href: '/events/', group: 'out' },
  { key: 'places', title: 'Places', subtitle: 'Eat, drink & stay', icon: 'restaurant', color: '#E53935', href: '/places/', group: 'out' },
  { key: 'visitor', title: 'Visitor Guide', subtitle: 'Attractions & beaches', icon: 'explore', color: '#F4511E', href: '/visitor/', group: 'out' },
  { key: 'astronomy', title: 'Night Sky', subtitle: 'Stargazing tonight', icon: 'nights_stay', color: '#2E3A87', href: '/night-sky/', group: 'out' },
  { key: 'toilets', title: 'Public Toilets', subtitle: 'Locations & access', icon: 'wc', color: '#00695C', href: '/toilets/', group: 'out' },
  { key: 'races', title: 'Race Schedule', subtitle: 'TT & Manx GP', icon: 'sports_motorsports', color: '#D84315', href: '/races/', group: 'out' },

  { key: 'emergency', title: 'Emergency', subtitle: 'Urgent numbers', icon: 'emergency', color: '#CF1020', href: '/emergency/', group: 'info' },
  { key: 'pharmacy', title: 'Pharmacies', subtitle: 'Rota & directory', icon: 'local_pharmacy', color: '#2E7D32', href: '/pharmacy/', group: 'info' },
  { key: 'school_terms', title: 'School Terms', subtitle: 'Term dates', icon: 'school', color: '#5D4037', href: '/school-terms/', group: 'info' },
  { key: 'bank_holidays', title: 'Bank Holidays', subtitle: 'Public holidays', icon: 'flag', color: '#AD1457', href: '/bank-holidays/', group: 'info' },
  { key: 'forms', title: 'Gov Forms', subtitle: 'Apply & report online', icon: 'description', color: '#455A64', href: '/forms/', group: 'info' },
];

export function sections(features: Record<string, { enabled: boolean }> = {}): Section[] {
  return ALL.filter((s) => {
    if (s.key === 'christmas' && !christmasInSeason()) return false;
    const f = features[s.key];
    return !(f && f.enabled === false);
  });
}

export function section(key: string): Section {
  return ALL.find((s) => s.key === key)!;
}
