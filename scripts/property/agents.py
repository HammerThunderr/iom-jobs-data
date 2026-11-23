"""
scrapers/property/agents.py — the agent registry.

For each provider, verify robots.txt and the listing URL pattern before enabling.
Chrystals is currently the active provider and uses the site's section indexes.
"""

import os
import re
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

    # Optional regex on the URL path that marks a listing page. Used when the
    # listing pages share a prefix with the index (Grays: /listings and
    # /listings/residential_sale-RX123-isle-of-man).
    listing_pattern: Optional[str] = None

    # Filled in during discovery: listing URL -> index URL it was found on.
    origin: dict = field(default_factory=dict)

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
        if self.page_mode == "path":
            from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
            parts = urlsplit(index_url)
            path = parts.path.rstrip("/") + f"/page/{page_num + 1}/"
            return urlunsplit((parts.scheme, parts.netloc, path, urlencode(parse_qsl(parts.query)), parts.fragment))
        separator = "&" if "?" in index_url else "?"
        return f"{index_url}{separator}{self.page_param}={page_num + 1}"

    def is_listing(self, url):
        path = urlparse(url).path
        if not path or path == "/":
            return False
        if any(path.startswith(prefix) for prefix in self.exclude_paths):
            return False
        if self.listing_pattern:
            return re.search(self.listing_pattern, path) is not None
        if self.property_path:
            return self.property_path in path
        if self.root_level_slugs:
            return path.strip("/").count("/") == 0
        return False


AGENTS = [
    # Black Grace Cowley moved to bgc.im (Nov 2026). robots.txt allows
    # everything except /wp-admin/. Section indexes paginate /page/2/ ...;
    # listings live at /property/<slug>/. The page breadcrumb says
    # "Residential / Buy" etc., which the parser uses for category and type.
    Agent(
        key="bgc",
        name="Black Grace Cowley",
        base="https://bgc.im",
        enabled=True,
        property_path="/property/",
        index_paths=(
            "/residential/buy/",
            "/residential/rent/",
            "/commercial/buy/",
            "/commercial/rent/",
        ),
        page_mode="path",
        max_pages=30,
        sitemap=None,
        search_path=None,
    ),

    # Cowley Groves (Douglas & Ramsey). robots.txt allows everything. The
    # search pages fill in by JavaScript, but sitemap.xml lists every
    # property page; each page shows its status, and completed sales/lets
    # are skipped by the parser.
    Agent(
        key="cg",
        name="Cowley Groves",
        base="https://www.cowleygroves.com",
        enabled=True,
        property_path="/property/",
        sitemap="/sitemap.xml",
    ),

    # Garforth Gray. robots.txt allows everything. The /sales, /rentals and
    # commercial pages load their results from the site's own public results
    # URL (the same one the page calls), which paginates with &page=N and
    # links to listings at /<area>-<street>/.
    Agent(
        key="gg",
        name="Garforth Gray",
        base="https://www.garforthgray.im",
        enabled=True,
        listing_pattern=r"^/[a-z0-9]+(?:-[a-z0-9]+)+/$",
        exclude_paths=("/dashboard", "/sales", "/rentals", "/commercial", "/auth",
                       "/about", "/awards", "/careers", "/contact", "/cookie",
                       "/disclaimer", "/privacy", "/terms", "/complaints",
                       "/anti-bribery", "/luxury", "/rent-your", "/sell-a", "/assets"),
        index_paths=(
            "/assets/inc/ajax.php?submitform=1&order=latest&keyword=&ajaxGetSaleResults=1&excludeSold=1",
            "/assets/inc/ajax.php?submitform=1&order=latest&keyword=&ajaxGetRentalsResults=1",
            "/assets/inc/ajax.php?submitform=1&order=latest&keyword=&ajaxGetCommercialResults=1",
        ),
        page_mode="page",
        page_param="page",
        max_pages=30,
        sitemap=None,
        search_path=None,
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

    # DeanWood uses individual property pages at /property/<slug>/ and
    # current section indexes with URL-path pagination (/page/2/, /page/3/).
    # Keeping this as an Agent entry means there is no separate DeanWood
    # scraper module. The shared parser has a DeanWood branch for its header.
    Agent(
        key="dw",
        name="DeanWood",
        base="https://deanwood.im",
        enabled=True,
        property_path="/property/",
        index_paths=(
            "/search/department/residential-sales/",
            "/search/department/residential-lettings/",
            "/search/department/commercial/",
        ),
        page_mode="path",
        max_pages=30,
        sitemap=None,
        search_path=None,
        url_rules=(
            ("/property/", "residential", None),
        ),
    ),

    # Manxmove uses /properties/<sale|letting>/.../ for individual listings.
    # The public search list is current and paginates as /page/2/, /page/3/.
    # The letting taxonomy is also a live index of current rental listings.
    # Keep both as index discovery so old sitemap entries are not the primary
    # source of listings.
    Agent(
        key="mm",
        name="Manxmove",
        base="https://www.manxmove.im",
        enabled=True,
        property_path="/properties/",
        index_paths=(
            "/search-list/",
            "/instruction-type/letting/",
        ),
        page_mode="path",
        max_pages=30,
        sitemap="/sitemap_index.xml",
        search_path=None,
        url_rules=(
            ("/properties/letting/", "residential", "rent"),
            ("/properties/sale/", "residential", "sale"),
        ),
    ),

    # Grays Estate Agents, Peel (Rex website). robots.txt allows everything.
    # /listings paginates with ?page=2; each listing's slug says what it is:
    # /listings/residential_sale-RX826035-isle-of-man.
    Agent(
        key="grays",
        name="Grays Estate Agents",
        base="https://graysestateagents.com",
        enabled=True,
        listing_pattern=r"^/listings/[a-z_]+-RX\d+",
        index_paths=(
            "/listings",
            "/listings?saleOrRental=Rental",
        ),
        page_mode="page",
        page_param="page",
        max_pages=20,
        sitemap=None,
        search_path=None,
        url_rules=(
            ("/listings/residential_sale", "residential", "sale"),
            ("/listings/residential_rental", "residential", "rent"),
            ("/listings/commercial_sale", "commercial", "sale"),
            ("/listings/commercial_rental", "commercial", "rent"),
            ("/listings/land_sale", "land", "sale"),
            ("/listings/rural_sale", "land", "sale"),
        ),
    ),

    # Partners Real Estate, Douglas (formerly Property Wise; propertywise.co.im
    # now redirects here). No robots.txt rules. Sections paginate ?page=2;
    # listings are /property/<n>-bed-for-sale-in-<address>/<id>.
    Agent(
        key="pre",
        name="Partners Real Estate",
        base="https://www.partners.co.im",
        enabled=True,
        listing_pattern=r"^/property/[^/]+/\d+/?$",
        exclude_paths=("/estateapps/",),
        index_paths=(
            "/property-for-sale",
            "/property-to-rent",
            "/commercial-property-for-sale",
            "/commercial-properties-to-rent",
        ),
        page_mode="page",
        page_param="page",
        max_pages=20,
        sitemap=None,
        search_path=None,
    ),
]


def active_agents():
    """Enabled agents. PROPERTY_AGENTS=bgc,grays limits a run to those keys
    (for testing a new agent without re-scraping everyone)."""
    only = {k.strip() for k in os.environ.get("PROPERTY_AGENTS", "").split(",") if k.strip()}
    return [a for a in AGENTS if a.enabled and (not only or a.key in only)]
