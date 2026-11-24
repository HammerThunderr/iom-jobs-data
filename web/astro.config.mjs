import { defineConfig } from 'astro/config';

// SITE_URL is the public address, used for canonical links and the sitemap.
export default defineConfig({
  site: process.env.SITE_URL || 'https://manxone-web.pages.dev',
  output: 'static',
  trailingSlash: 'ignore',
  build: { format: 'directory' },
  compressHTML: true,
});
