// Builds a one-event .ics file and downloads it.
export function downloadIcs(o: { title: string; date: string; endDate?: string; time?: string; minutes?: number; where?: string; url?: string; description?: string }) {
  const clean = (s = '') => s.replace(/[\\;,]/g, (c) => '\\' + c).replace(/\n/g, '\\n');
  const ymd = (d: string) => d.replace(/-/g, '');
  const lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Manx One//EN', 'BEGIN:VEVENT', `UID:${Date.now()}-${Math.random().toString(36).slice(2)}@manxone`, `DTSTAMP:${new Date().toISOString().replace(/[-:]/g, '').replace(/\.\d+/, '')}`];
  if (o.time) {
    const [h, m] = o.time.split(':').map(Number);
    const start = `${ymd(o.date)}T${String(h).padStart(2, '0')}${String(m).padStart(2, '0')}00`;
    const endMin = h * 60 + m + (o.minutes ?? 120);
    const end = `${ymd(o.date)}T${String(Math.min(23, Math.floor(endMin / 60))).padStart(2, '0')}${String(endMin >= 1440 ? 59 : endMin % 60).padStart(2, '0')}00`;
    lines.push(`DTSTART;TZID=Europe/London:${start}`, `DTEND;TZID=Europe/London:${end}`);
  } else {
    const end = new Date((o.endDate || o.date) + 'T12:00:00Z');
    end.setUTCDate(end.getUTCDate() + 1);
    lines.push(`DTSTART;VALUE=DATE:${ymd(o.date)}`, `DTEND;VALUE=DATE:${ymd(end.toISOString().slice(0, 10))}`);
  }
  lines.push(`SUMMARY:${clean(o.title)}`);
  if (o.where) lines.push(`LOCATION:${clean(o.where)}`);
  if (o.url) lines.push(`URL:${o.url}`);
  if (o.description) lines.push(`DESCRIPTION:${clean(o.description)}`);
  lines.push('END:VEVENT', 'END:VCALENDAR');
  const blob = new Blob([lines.join('\r\n')], { type: 'text/calendar' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = o.title.replace(/[^\w]+/g, '-').slice(0, 50) + '.ics';
  document.body.appendChild(a);
  a.click();
  setTimeout(() => {
    URL.revokeObjectURL(a.href);
    a.remove();
  }, 500);
}
