"""
scrapers/property/run.py — entry point for the property scraper.

Runs every enabled agent in agents.py, merges the results with the previous
run, and writes a single properties.json for the Manx One app.

Usage:
    pip install requests beautifulsoup4
    python scrapers/property/run.py                 # writes ./properties.json
    OUTPUT_PATH=docs/property/properties.json python scrapers/property/run.py

One agent failing never kills the run: its previous listings are carried over
and flagged stale, and the failure is recorded in meta.sources.
"""

import json
import re
import sys
from datetime import datetime, timezone

import common
from agents import active_agents

DISCLAIMER = (
    "Listings collected from Isle of Man estate agent websites. Always confirm "
    "price, status and availability with the agent. Manx One is not an estate "
    "agent and is not affiliated with any agency listed."
)


def _absolute(agent, href):
    url = href if href.startswith("http") else agent.base + href
    return url.split("?")[0].rstrip("/") + "/"


def discover_via_sitemap(agent):
    """WordPress/most CMS sitemaps list listing URLs even when APIs are shut."""
    urls = set()
    if not agent.sitemap_url:
        return urls

    index = common.get(agent.sitemap_url)
    if not index:
        return urls

    locs = re.findall(r"<loc>\s*([^<]+?)\s*</loc>", index.text)
    # A sitemap index points at sub-sitemaps; a flat sitemap lists pages.
    direct = {_absolute(agent, l) for l in locs if agent.property_path in l}
    if direct:
        urls |= direct

    subs = [l for l in locs if l.endswith(".xml")]
    for sub in subs:
        # Only fetch sub-sitemaps that plausibly hold listings.
        if subs and agent.property_path.strip("/") not in sub.lower():
            continue
        page = common.get(sub)
        if not page:
            continue
        urls |= {
            _absolute(agent, l)
            for l in re.findall(r"<loc>\s*([^<]+?)\s*</loc>", page.text)
            if agent.property_path in l
        }
    return urls


def discover_via_search(agent):
    """Fallback: walk the site's own search/results pages."""
    urls = set()
    if not agent.search_url:
        return urls

    for page_num in range(1, agent.max_pages + 1):
        params = dict(agent.search_params)
        if agent.page_param:
            params[agent.page_param] = page_num

        res = common.get(agent.search_url, params=params)
        if not res:
            break

        pattern = rf'href="([^"]*?{re.escape(agent.property_path)}[^"]+?)"'
        found = {_absolute(agent, h) for h in re.findall(pattern, res.text)}
        fresh = found - urls
        print(f"    search page {page_num}: +{len(fresh)}")
        if not fresh:
            break
        urls |= found
    return urls


def run_agent(agent):
    """Scrape one agent. Raises on total failure so the caller can mark it."""
    print(f"\n=== {agent.name} ===")

    urls = discover_via_sitemap(agent)
    if urls:
        print(f"  sitemap: {len(urls)} listing URLs")
    else:
        print("  sitemap empty — trying search endpoint")
        urls = discover_via_search(agent)
        print(f"  search: {len(urls)} listing URLs")

    if not urls:
        raise RuntimeError("no listing URLs discovered")

    listings = []
    for i, url in enumerate(sorted(urls), 1):
        print(f"  [{i}/{len(urls)}] {url}")
        item = common.scrape_listing(agent, url)
        if item:
            listings.append(item)

    if not listings:
        raise RuntimeError("URLs found but nothing parsed")
    return listings


def main():
    print(f"Manx One property scraper\nIdentifying as: {common.USER_AGENT}")

    previous = common.load_previous()
    print(f"Previous run: {len(previous)} listings")

    all_listings, sources, failed = [], [], []

    for agent in active_agents():
        try:
            listings = run_agent(agent)
            all_listings.extend(listings)
            priced = sum(1 for l in listings if l["price"])
            sources.append({
                "agent": agent.name,
                "count": len(listings),
                "withPrice": priced,
                "status": "ok",
            })
            print(f"  -> {len(listings)} listings ({priced} priced)")
        except Exception as exc:                     # noqa: BLE001
            # Never let one agent take down the whole feed.
            print(f"  !! {agent.name} FAILED: {exc}")
            failed.append(agent.name)
            sources.append({
                "agent": agent.name,
                "count": 0,
                "status": "failed",
                "error": str(exc),
            })

    merged = common.merge(all_listings, previous, failed)

    payload = {
        "meta": {
            "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "sources": sources,
            "disclaimer": DISCLAIMER,
        },
        "listings": merged,
    }

    with open(common.OUTPUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)

    print(f"\nWrote {len(merged)} listings to {common.OUTPUT}")
    for src in sources:
        print(f"  {src['status']:7} {src['agent']}: {src['count']}")

    # Fail the CI run if every agent broke — better a red build than bad data.
    if failed and len(failed) == len(active_agents()):
        sys.exit("ABORT: all agents failed")


if __name__ == "__main__":
    main()
