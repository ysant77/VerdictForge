from __future__ import annotations

from dataclasses import dataclass
from typing import List
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse

from bs4 import BeautifulSoup
import re


@dataclass
class ListingPage:
    page_num: int
    judgment_urls: List[str]


def build_listing_url(base_listing_url: str, page_num: int) -> str:
    """
    Build listing URL for eLitigation listing pages.

    Works for:
      - https://www.elitigation.sg/gdviewer/SUPCT
      - https://www.elitigation.sg/gd/Home/Index?Filter=SUPCT
      - https://www.elitigation.sg/gd/
    """
    u = urlparse(base_listing_url)
    q = parse_qs(u.query)

    # Many listing endpoints support this query param for pagination.
    q["CurrentPage"] = [str(page_num)]

    # Keep these conservative; if the endpoint ignores them it’s fine.
    q.setdefault("PageSize", ["0"])
    q.setdefault("SortBy", ["DateOfDecision"])
    q.setdefault("SortAscending", ["False"])

    query = urlencode(q, doseq=True)
    return urlunparse((u.scheme, u.netloc, u.path, u.params, query, u.fragment))


def parse_listing_html(source_base_url: str, html: str, page_num: int) -> ListingPage:
    """
    Extract judgment URLs from a listing HTML page.

    IMPORTANT: the site uses both:
      - /gd/s/<slug>
      - /gdviewer/s/<slug>
    so we match both patterns.
    """
    urls: set[str] = set()

    soup = BeautifulSoup(html, "lxml")

    # 1) Standard anchors
    for a in soup.select("a[href]"):
        href = a.get("href") or ""
        if "/gd/s/" in href or "/gdviewer/s/" in href:
            urls.add(urljoin(source_base_url, href))

    # 2) Fallback: scan raw HTML (handles onclick, data-href, embedded text)
    patterns = [
        r"/gd/s/[A-Za-z0-9_\-]+",
        r"/gdviewer/s/[A-Za-z0-9_\-]+",
    ]
    for pat in patterns:
        for m in re.finditer(pat, html):
            urls.add(urljoin(source_base_url, m.group(0)))

    return ListingPage(page_num=page_num, judgment_urls=sorted(urls))
