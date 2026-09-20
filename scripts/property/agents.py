"""
scrapers/property/agents.py — the agent registry.

For each provider, verify robots.txt and the listing URL pattern before enabling.
Chrystals is currently the active provider and uses the site's section indexes.
"""

from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse


@dataclass
class Agent:
    key: str
    name: str
    base: str

    property_path: Optional[str] = None
    root_level_slugs: bool = False
    exclude_paths: tuple = ()
    require_lastmod: bool = False

    sitemap: Optional[str] = None
    search_path: Optional[str] = None
    search_params: dict = field(default_factory=dict)
    page_param: Optional[str] = "page"
    max_pages: int = 30
    enabled: bool = True

    index_paths: tuple = ()
    page_mode: str = "page"
    offset_param: str = "start"
    page_size: int = 20

    url_rules: tuple = ()

    def classify(self, url):
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

    @property
    def index_urls(self):
        return [f"{self.base}{p}" for p in self.index_paths]

    def index_page_url(self, index_url, page_num):
        if page_num == 0:
            return index_url
        if self.page_mode == "offset":
            separator = "&" if "?" in index_url else "?"
            return f"{index_url}{separator}{self.offset_param}={page_num * self.page_size}"
        separator = "&" if "?" in index_url else "?"
        return f"{index_url}{separator}{self.page_param}={page_num + 1}"

    def is_listing(self, url):
        path = urlparse(url).path
        if not path or path == "/":
            return False
        if any(path.startswith(prefix) for prefix in self.exclude_paths):
            return False
        if self.property_path:
            return self.property_path in path
        if self.root_level_slugs:
            return path.strip("/").count("/") == 0
        return False


AGENTS = [
    # robots.txt checked previously: listings crawlable. Paused while testing
    # providers one at a time.
    Agent(
        key="bgc",
        name="Black Grace Cowley",
        base="https://www.blackgracecowley.com",
        enabled=False,
        property_path="/property/",
        sitemap="/wp-sitemap.xml",
        search_path="/search/",
        search_params={
            "PropertySearch[searchType]": "1",
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

    Agent(
        key="cg",
        name="Cowley Groves",
        base="https://www.cowleygroves.com",
        enabled=False,
        property_path="/property/",
        sitemap="/sitemap.xml",
    ),

    Agent(
        key="gg",
        name="Garforth Gray",
        base="https://www.garforthgray.im",
        enabled=False,
        root_level_slugs=True,
        require_lastmod=True,
        exclude_paths=("/sales/", "/rentals/", "/dashboard/", "/commercials/"),
        sitemap="/sitemap.php",
    ),

    # Chrystals / Expert Agent.
    # The public section pages expose current catalogue entries and paginate
    # with ?start=18, ?start=36, ... . Their sitemap also contains many stale
    # property pages, so indexes are deliberately the primary discovery route.
    Agent(
        key="chr",
        name="Chrystals",
        base="https://www.chrystals.co.im",
        enabled=True,
        property_path="/property/",
        index_paths=(
            "/properties-for-sale",
            "/properties-to-let",
            "/commercial/commercial-sales",
            "/commercial/commercial-lettings",
            "/agricultural",
            "/developments",  # Chrystals labels this section "Building Plots"
        ),
        page_mode="offset",
        offset_param="start",
        page_size=18,
        sitemap=None,
        search_path=None,
        exclude_paths=(
            "/properties/agentproperties/",
            "/components/", "/component/", "/modules/", "/administrator/",
        ),
        url_rules=(
            ("/commercial/commercial-lettings/", "commercial", "rent"),
            ("/commercial/commercial-sales/", "commercial", "sale"),
            ("/agricultural/", "land", "sale"),
            ("/developments/", "land", "sale"),
            ("/properties-for-sale/", "residential", "sale"),
            ("/properties-to-rent/", "residential", "rent"),
            ("/properties-to-let/", "residential", "rent"),
        ),
    ),
]


def active_agents():
    return [a for a in AGENTS if a.enabled]
