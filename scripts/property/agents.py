"""
scrapers/property/agents.py — the agent registry.

TO ADD A NEW PROVIDER:
  1. Check <site>/robots.txt first. If listings paths are Disallowed, STOP —
     email the agent instead of scraping them.
  2. Open one property page and note the URL pattern (the bit before the slug,
     e.g. /property/, /properties/, /for-sale/).
  3. Add an Agent(...) entry below. No new code needed in most cases — the
     extraction in common.py is heuristic, so it works across sites.
  4. Run locally and check the per-agent counts before committing.

Discovery order per agent: sitemap first (cheap, complete), then the site's
own search endpoint as a fallback.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Agent:
    key: str                     # short id, used as the listing id prefix
    name: str                    # display name shown in the app
    base: str                    # site root, no trailing slash
    property_path: str           # marker identifying a listing URL
    sitemap: Optional[str] = None        # path to sitemap or sitemap index
    search_path: Optional[str] = None    # fallback listing-index page
    search_params: dict = field(default_factory=dict)  # template; {page} filled
    page_param: Optional[str] = "page"   # pagination query key
    max_pages: int = 30
    enabled: bool = True

    @property
    def sitemap_url(self):
        return f"{self.base}{self.sitemap}" if self.sitemap else None

    @property
    def search_url(self):
        return f"{self.base}{self.search_path}" if self.search_path else None


AGENTS = [
    # robots.txt checked: only /wp-admin/ disallowed, listings crawlable.
    # WordPress site; the `property` post type is NOT exposed over REST, so we
    # parse the pages. Their search params were found in their own page links.
    Agent(
        key="bgc",
        name="Black Grace Cowley",
        base="https://www.blackgracecowley.com",
        property_path="/property/",
        sitemap="/wp-sitemap.xml",
        search_path="/search/",
        search_params={
            "PropertySearch[searchType]": "1",   # 1 = sales; 2 likely lettings
            "PropertySearch[minPrice]": "0",
            "PropertySearch[maxPrice]": "99999999",
            "PropertySearch[term]": "",
            "PropertySearch[sortOrder]": "",
            "PropertySearch[bedroom]": "",
            "PropertySearch[reception]": "",
            "PropertySearch[propertyType]": "",
            "PropertySearch[area]": "",
        },
    ),

    # ---- Add further agents below once robots.txt is verified ----
    # Fill in property_path from a real listing URL before enabling.
    #
    # Agent(
    #     key="chrystals",
    #     name="Chrystals",
    #     base="https://www.chrystals.co.im",
    #     property_path="/property/",
    #     sitemap="/sitemap.xml",
    #     enabled=False,
    # ),
    # Agent(
    #     key="cowleygroves",
    #     name="Cowley Groves",
    #     base="https://www.cowleygroves.com",
    #     property_path="/property/",
    #     sitemap="/sitemap.xml",
    #     enabled=False,
    # ),
    # Agent(
    #     key="garforthgray",
    #     name="Garforth Gray",
    #     base="https://www.garforthgray.im",
    #     property_path="/property/",
    #     sitemap="/sitemap.xml",
    #     enabled=False,
    # ),
]


def active_agents():
    return [a for a in AGENTS if a.enabled]
