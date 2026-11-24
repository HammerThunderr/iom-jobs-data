# Manx One website

The Manx One website, built with [Astro](https://astro.build) from the same
data as the app (the JSON files in `../docs`). Every page is plain HTML with a
little JavaScript for search, filters and live data.

## Run it on your computer

```
cd web
npm install
npm run dev
```

Then open http://localhost:4321.

## Build

```
npm run build
```

The finished site is in `web/dist`.

## Publishing

`.github/workflows/website.yml` builds the site every 2 hours and whenever
`web/` changes, then publishes it to the Cloudflare Pages project
`manxone-web` — once the repository has the `CLOUDFLARE_API_TOKEN` and
`CLOUDFLARE_ACCOUNT_ID` secrets.

To publish by hand instead:

```
npm run build
npx wrangler pages deploy dist --project-name=manxone-web
```

## Where things are

- `src/pages/` — one file per page (`jobs/[slug].astro` makes a page per job)
- `src/lib/` — data loading and shared logic (bus planner, weather, events…)
- `src/layouts/Layout.astro` — header, menu and footer
- `src/styles/global.css` — colours, light/dark mode and shared styles
- `scripts/` — copies the data into the site and picks the icons it uses
