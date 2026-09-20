"""
scrapers/property/run.py — entry point for the property scraper.

Discovery order is intentionally:
  1. agent section indexes (current listings only)
  2. sitemap (if configured)
  3. site's own search endpoint (fallback)

This matters for Chrystals because its sitemap contains many archived/dead
property URLs, while its section indexes expose the current catalogue.
"""

import json
import sys
from datetime import datetime, timezone
from urllib.parse import urljoin

from bs4 import BeautifulSoup

import common
from agents import active_agents

DISCLAIMER = (
    "Listings collected from Isle of Man estate agent websites. Always confirm "
    "price, status and availability with the agent. Manx One is not an estate "
    "agent and is not affiliated with any agency listed."
)


def _absolute(agent, href):
    return urljoin(agent.base + "/", href).split("#", 1)[0].split("?", 1)[0].rstrip("/") + "/"


def _add_param(url, key, value):
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{key}={value}"


def discover_via_index(agent):
    """Walk the configured section indexes and collect listing URLs."""
    urls = set()
    if not agent.index_urls:
        return urls

    for index_url in agent.index_urls:
        print(f"  index: {index_url}")
        seen_on_section = set()

        for page_num in range(agent.max_pages):
            page_url = agent.index_page_url(index_url, page_num)
            res = common.get(page_url)
            if not res:
                break

            soup = BeautifulSoup(res.text, "html.parser")
            found = set()
            for link in soup.select("a[href]"):
                href = link.get("href", "").strip()
                if not href or href.startswith(("#", "javascript:", "mailto:")):
                    continue
                full = _absolute(agent, href)
                if agent.is_listing(full):
                    found.add(full)

            fresh = found - seen_on_section
            print(f"    page {page_num + 1}: +{len(fresh)}")
            if not fresh:
                break

            urls |= fresh
            seen_on_section |= found

    return urls


def sitemap_entries(text):
    """Yield (loc, lastmod_or_None) for each <url> block in a sitemap."""
    import re

    for block in re.findall(r"<url>(.*?)</url>", text, flags=re.S | re.I):
        loc = re.search(r"<loc>\s*([^<]+?)\s*</loc>", block, flags=re.I)
        if not loc:
            continue
        lastmod = re.search(r"<lastmod>\s*([^<]+?)\s*</lastmod>", block, flags=re.I)
        yield loc.group(1), (lastmod.group(1) if lastmod else None)


def _accept(agent, loc, lastmod):
    if agent.require_lastmod and not lastmod:
        return False
    return agent.is_listing(loc)


def discover_via_sitemap(agent):
    urls = set()
    if not agent.sitemap_url:
        return urls

    index = common.get(agent.sitemap_url)
    if not index:
        return urls

    entries = list(sitemap_entries(index.text))
    urls |= {_absolute(agent, loc) for loc, lastmod in entries if _accept(agent, loc, lastmod)}

    subs = [loc for loc, _ in entries if loc.lower().endswith(".xml")]
    for sub in subs:
        if agent.property_path and agent.property_path.strip("/").lower() not in sub.lower():
            continue
        page = common.get(sub)
        if not page:
            continue
        urls |= {
            _absolute(agent, loc)
            for loc, lastmod in sitemap_entries(page.text)
            if _accept(agent, loc, lastmod)
        }
    return urls


def discover_via_search(agent):
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

        soup = BeautifulSoup(res.text, "html.parser")
        found = set()
        for link in soup.select("a[href]"):
            href = link.get("href", "").strip()
            if not href:
                continue
            full = _absolute(agent, href)
            if agent.is_listing(full):
                found.add(full)

        fresh = found - urls
        print(f"    search page {page_num}: +{len(fresh)}")
        if not fresh:
            break
        urls |= fresh
    return urls


def run_agent(agent):
    print(f"\n=== {agent.name} ===")

    urls = discover_via_index(agent)
    if urls:
        print(f"  index: {len(urls)} listing URLs")
    else:
        print("  index empty — trying sitemap")
        urls = discover_via_sitemap(agent)

    if not urls:
        print("  sitemap empty — trying search endpoint")
        urls = discover_via_search(agent)

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
        except Exception as exc:  # noqa: BLE001
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

    if failed and len(failed) == len(active_agents()):
        sys.exit("ABORT: all agents failed")


if __name__ == "__main__":
    main()
