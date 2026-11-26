// Ready-written driving lesson requests (same wording as the app).
export type LessonRequest = {
  name: string;
  phone: string;
  car: 'manual' | 'automatic' | 'either';
  area: string;
  experience: string;
  frequency: string;
  times: string[];
  notes: string;
};

export const EXPERIENCE = ['Complete beginner', "I've had a few lessons", 'Nearly ready for my test', 'Test already booked', 'Qualified driver wanting a refresher'];
export const FREQUENCY = ['Weekly lessons', 'Twice a week', 'Intensive course', 'One-off lesson'];
export const TIMES = ['Weekday daytime', 'Weekday evenings', 'Weekends'];

export const carLabel = (r: LessonRequest) => (r.car === 'automatic' ? 'Automatic' : r.car === 'either' ? 'Manual or automatic' : 'Manual');
const timesLabel = (r: LessonRequest) => (r.times.length ? r.times.join(', ').toLowerCase() : 'flexible');

/** "Mr G Kirby" -> "Mr Kirby"; null for anything that isn't a simple name. */
export function greetingName(registerName: string): string | null {
  const parts = registerName.trim().split(/\s+/);
  const title = (parts[0] || '').replace('.', '');
  if (parts.length < 2 || parts.length > 4 || !['Mr', 'Mrs', 'Ms', 'Miss', 'Dr', 'Mx'].includes(title)) return null;
  const surname = parts[parts.length - 1];
  return surname.length < 2 ? null : `${title} ${surname}`;
}

export const subject = (r: LessonRequest) => `Driving lessons enquiry – ${carLabel(r).toLowerCase()}, ${r.area}`;

export function body(r: LessonRequest, instructor: string): string {
  const hello = greetingName(instructor);
  return [
    hello ? `Hello ${hello},` : 'Hello,',
    '',
    "I found your details on the Isle of Man Government's register of approved driving instructors, and I'm looking for driving lessons.",
    '',
    `• Car: ${carLabel(r)}`,
    `• Area: ${r.area}`,
    `• Experience: ${r.experience}`,
    `• Looking for: ${r.frequency}`,
    `• Best times: ${timesLabel(r)}`,
    ...(r.notes.trim() ? ['', r.notes.trim()] : []),
    '',
    'Do you have space for a new learner? Could you let me know your prices and when you could start?',
    '',
    'Thank you,',
    r.name.trim(),
    ...(r.phone.trim() ? [r.phone.trim()] : []),
  ].join('\n');
}

export function sms(r: LessonRequest, instructor: string): string {
  const hello = greetingName(instructor);
  return `${hello ? `Hi ${hello}` : 'Hello'}, I found you on the IOM approved driving instructor list. I'm looking for ${carLabel(r).toLowerCase()} lessons in ${r.area} (${r.experience.toLowerCase()}, ${r.frequency.toLowerCase()}, best times: ${timesLabel(r)}). Do you have space for a new learner, and what are your prices? Thanks, ${r.name.trim()}`;
}

export const mailto = (to: string, r: LessonRequest, instructor: string) =>
  `mailto:${to}?subject=${encodeURIComponent(subject(r))}&body=${encodeURIComponent(body(r, instructor))}`;

export const gmail = (to: string, r: LessonRequest, instructor: string) =>
  `https://mail.google.com/mail/?view=cm&fs=1&to=${encodeURIComponent(to)}&su=${encodeURIComponent(subject(r))}&body=${encodeURIComponent(body(r, instructor))}`;

export const smsHref = (phone: string, r: LessonRequest, instructor: string) => {
  const ios = /iPhone|iPad|iPod/i.test(navigator.userAgent);
  return `sms:${phone}${ios ? '&' : '?'}body=${encodeURIComponent(sms(r, instructor))}`;
};
