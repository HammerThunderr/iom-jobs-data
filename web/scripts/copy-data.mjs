// Copies the data feeds into public/data so the site can read them in the
// browser too. DATA_DIR defaults to ../docs (this repo's GitHub Pages folder).
import fs from 'node:fs';
import path from 'node:path';

const src = path.resolve(process.env.DATA_DIR || '../docs');
const dest = path.resolve('public/data');

fs.rmSync(dest, { recursive: true, force: true });
fs.mkdirSync(dest, { recursive: true });

let n = 0;
function copy(from, to) {
  for (const entry of fs.readdirSync(from, { withFileTypes: true })) {
    const a = path.join(from, entry.name);
    const b = path.join(to, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === 'social') continue;
      fs.mkdirSync(b, { recursive: true });
      copy(a, b);
    } else if (entry.name.endsWith('.json')) {
      fs.copyFileSync(a, b);
      n++;
    }
  }
}
copy(src, dest);
console.log(`copy-data: ${n} files from ${src}`);
