// Turns the scraped JobCentre and JobTrain text into tidy fields.
import { load } from './data';
import { slugify } from './format';

export type Job = {
  id: string;
  slug: string;
  title: string;
  employer: string;
  category: string;
  hours: string;
  duration: string;
  salary: string;
  address: string;
  closing: string; // display text
  closingIso: string | null;
  contactName: string;
  email: string;
  phone: string;
  notes: string;
  url: string;
  number: string;
};

const JC_LABELS = ['Reference ID', 'Job title', 'Number Required', 'Firm', 'Hours', 'Address', 'Duration', 'Contact', 'Salary', 'Tel No', 'End Date', 'Notes'];

function parseLabelled(text: string, labels: string[]): Record<string, string> {
  const out: Record<string, string> = {};
  const lines = String(text || '').split('\n');
  let key: string | null = null;
  let buf: string[] = [];
  const flush = () => {
    if (key && !(key in out)) out[key] = buf.join('\n').trim();
    buf = [];
  };
  for (const raw of lines) {
    const line = raw.trim();
    const label = labels.find((l) => line === l || line === l + ':');
    if (label && key !== 'Notes') {
      flush();
      key = label;
      continue;
    }
    if (key === 'Notes' && /^Signposts - DESC/.test(line)) break;
    if (key) buf.push(raw);
  }
  flush();
  return out;
}

/** Re-flow text that was scraped one DOM node per line. */
export function reflow(text: string): string {
  const lines = String(text || '').split('\n').map((l) => l.trim());
  const out: string[] = [];
  for (let i = 0; i < lines.length; i++) {
    let line = lines[i];
    if (!line) {
      if (out.length && out[out.length - 1] !== '') out.push('');
      continue;
    }
    if (line === '✔' || line === '•' || line === '-') {
      const next = lines[i + 1];
      if (next) {
        out.push('• ' + next);
        i++;
      }
      continue;
    }
    const prev = out[out.length - 1];
    if (prev && /^[,.;:!?)’']/.test(line)) {
      out[out.length - 1] = prev + line;
      continue;
    }
    if (prev && prev.length < 60 && !/[.!?:]$/.test(prev) && /^[a-z(]/.test(line) && !prev.startsWith('•')) {
      out[out.length - 1] = prev + ' ' + line;
      continue;
    }
    if (prev && /^[A-Z][a-z]+$/.test(prev) && prev.length < 4 && /^[A-Z]/.test(line)) {
      out[out.length - 1] = prev + ' ' + line;
      continue;
    }
    out.push(line);
  }
  return out.join('\n').replace(/\n{3,}/g, '\n\n').trim();
}

function ukDate(s: string): string | null {
  const t = String(s || '').trim();
  let m = t.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (m) return `${m[3]}-${m[2].padStart(2, '0')}-${m[1].padStart(2, '0')}`;
  const d = new Date(t + ' 12:00 UTC');
  return isNaN(d.getTime()) ? null : d.toISOString().slice(0, 10);
}

let jobsCache: Job[] | null = null;
export function jobs(): Job[] {
  if (jobsCache) return jobsCache;
  const raw = load<any>('jobs.json')?.jobs ?? [];
  const seen = new Set<string>();
  jobsCache = raw
    .map((j: any): Job => {
      const f = parseLabelled(j.fullDescription || j.rawText || '', JC_LABELS);
      const salary = f['Salary'] || (j.salary && j.salary !== 'To' ? j.salary : '');
      const closing = f['End Date'] || j.closingDate || '';
      const id = String(j.jobId || '');
      return {
        id,
        slug: `${slugify(j.title || f['Job title'] || 'job')}-${id}`,
        title: (j.title || f['Job title'] || 'Vacancy').trim(),
        employer: (j.employer || f['Firm'] || '').trim(),
        category: j.category || '',
        hours: (f['Hours'] || j.hours || '').trim(),
        duration: (f['Duration'] || '').trim(),
        salary: salary.trim(),
        address: (f['Address'] || '').replace(/\n+/g, ', ').trim(),
        closing,
        closingIso: ukDate(closing),
        contactName: (f['Contact'] || j.contactName || '').trim(),
        email: (j.contactEmail || '').trim(),
        phone: (f['Tel No'] || j.contactPhone || '').trim(),
        notes: reflow(f['Notes'] || j.duties || ''),
        url: j.url,
        number: f['Number Required'] || '',
      };
    })
    .filter((j: Job) => j.id && !seen.has(j.id) && seen.add(j.id));
  return jobsCache!;
}

export type GovJob = {
  id: string;
  slug: string;
  title: string;
  department: string;
  location: string;
  salary: string;
  type: string;
  hours: string;
  reference: string;
  closing: string;
  closingIso: string | null;
  advert: string;
  email: string;
  phone: string;
  url: string;
};

const GJ_LABELS = ['Job Reference:', 'Salary:', 'Closing Date:', 'Department:', 'Location:', 'Employment Type:', 'Hours Per Week:', 'Job Advert'];

let govCache: GovJob[] | null = null;
export function govJobs(): GovJob[] {
  if (govCache) return govCache;
  const raw = load<any>('gov_jobs.json')?.jobs ?? [];
  govCache = raw.map((j: any): GovJob => {
    const text = String(j.fullDescription || '');
    const f: Record<string, string> = {};
    const lines = text.split('\n');
    let advertStart = -1;
    for (let i = 0; i < lines.length; i++) {
      const l = lines[i].trim();
      if (l === 'Job Advert') {
        advertStart = i + 1;
        break;
      }
      if (GJ_LABELS.includes(l) && lines[i + 1] != null) f[l.replace(':', '')] = lines[i + 1].trim();
    }
    let advert = advertStart > 0 ? lines.slice(advertStart).join('\n') : text;
    advert = advert.replace(/\n(Apply for job|Share this job)[\s\S]*$/i, '');
    const id = String(j.jobId);
    const closing = j.closingDate || f['Closing Date'] || '';
    return {
      id,
      slug: `${slugify(j.title)}-${id}`,
      title: j.title,
      department: j.department || f['Department'] || '',
      location: j.location || f['Location'] || '',
      salary: j.salary || f['Salary'] || '',
      type: f['Employment Type'] || j.hours || '',
      hours: f['Hours Per Week'] || '',
      reference: f['Job Reference'] || '',
      closing,
      closingIso: ukDate(closing),
      advert: reflow(advert),
      email: j.contactEmail || '',
      phone: j.contactPhone || '',
      url: j.url,
    };
  });
  return govCache!;
}
