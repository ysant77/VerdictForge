from __future__ import annotations

from dataclasses import dataclass
from bs4 import BeautifulSoup


@dataclass(frozen=True)
class ParsedDocument:
    url: str
    text: str
    lines: list[str]


def parse_html(url: str, html: str) -> ParsedDocument:
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text("\n", strip=True)
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    return ParsedDocument(url=url, text=text, lines=lines)
