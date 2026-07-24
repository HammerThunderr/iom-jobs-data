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
from urllib.parse import urlparse


@dataclass
class Agent:
    key: str                     # short id, used as the listing id prefix
    name: str                    # display name shown in the app
    base: str                    # site root, no trailing slash

    # --- how to recognise a listing URL (use ONE of these) ---
    property_path: Optional[str] = None   # e.g. "/property/" — path contains this
    root_level_slugs: bool = False        # listings live at /some-slug/ (no prefix)

    # Extra filters, mainly for root_level_slugs sites where listings and
    # ordinary pages share the same URL shape.
    exclude_paths: tuple = ()             # path prefixes that are never listings
    require_lastmod: bool = False         # only sitemap entries with <lastmod>

    sitemap: Optional[str] = None         # path to sitemap or sitemap index
    search_path: Optional[str] = None     # fallback listing-index page
    search_params: dict = field(default_factory=dict)
    page_param: Optional[str] = "page"
    max_pages: int = 30
    enabled: bool = True

    # Some agents encode category/type in the URL itself, which is far more
    # reliable than guessing from page wording. First match wins.
    # Format: ((path_fragment, category, listing_type), ...)
    url_rules: tuple = ()

    def classify(self, url):
        """Return (category, listing_type) from the URL, or (None, None)."""
        path = urlparse(url).path
        for fragment, category, listing_type in self.url_rules:
            if fragment in path:
                return category, listing_type
        return None, None

    @property
    def sitemap_url(self):
        return f"{self.base}{self.sitemap}" if self.sitemap else None

    @property
    def search_url(self):
        return f"{self.base}{self.search_path}" if self.search_path else None

    def is_listing(self, url):
        """True if this URL looks like an individual property page."""
        path = urlparse(url).path
        if not path or path == "/":
            return False
        if any(path.startswith(prefix) for prefix in self.exclude_paths):
            return False
        if self.property_path:
            return self.property_path in path
        if self.root_level_slugs:
            # Exactly one path segment: /douglas-ballanard-road-7/
            return path.strip("/").count("/") == 0
        return False


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

    # robots.txt checked: "Disallow:" with no path = everything permitted.
    # Flat sitemap (not an index) listing every property URL directly, so one
    # request covers discovery. Slugs carry postcodes and some carry -rent/-sale.
    Agent(
        key="cg",
        name="Cowley Groves",
        base="https://www.cowleygroves.com",
        property_path="/property/",
        sitemap="/sitemap.xml",
    ),

    # robots.txt checked: "Disallow:" with no path = everything permitted.
    # Different shape to the others: listings sit at the ROOT (/douglas-elm-drive/)
    # with no /property/ prefix, alongside ordinary pages. Their sitemap only
    # puts <lastmod> on real listings — the homepage, /dashboard/ and the 100+
    # /sales/ SEO landing pages have none — so that is the discriminator.
    Agent(
        key="gg",
        name="Garforth Gray",
        base="https://www.garforthgray.im",
        root_level_slugs=True,
        require_lastmod=True,
        exclude_paths=("/sales/", "/rentals/", "/dashboard/", "/commercials/"),
        sitemap="/sitemap.php",     # note: .php, not .xml
    ),

    # robots.txt checked: Joomla site. Listing paths are permitted, but
    # /properties/agentproperties/ IS disallowed, so it is excluded below.
    # Flat sitemap. Their URL structure encodes category and sale/rent, which
    # is more reliable than reading the page — see url_rules.
    # Slugs are {numeric_id}-{address}, often with the address repeated twice.
    Agent(
        key="chr",
        name="Chrystals",
        base="https://www.chrystals.co.im",
        property_path="/property/",
        sitemap="/sitemap.xml",
        exclude_paths=(
            "/properties/agentproperties/",   # disallowed in robots.txt
            "/components/", "/component/", "/modules/", "/administrator/",
        ),
        url_rules=(
            ("/commercial/commercial-lettings/", "commercial", "rent"),
            ("/commercial/commercial-sales/", "commercial", "sale"),
            ("/agricultural/", "land", None),
            ("/developments/", "residential", "sale"),
            ("/properties-for-sale/", "residential", "sale"),
            ("/properties-to-rent/", "residential", "rent"),
            ("/properties-to-let/", "residential", "rent"),
        ),
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
