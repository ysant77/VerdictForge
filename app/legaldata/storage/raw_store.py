from __future__ import annotations

import hashlib
from pathlib import Path


class RawStore:
    """Stores raw HTML to disk. Keeps stable filenames for idempotency."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def slug_for_url(self, url: str) -> str:
        h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
        tail = url.rstrip("/").split("/")[-1]
        return f"{tail}_{h}"

    def write_html(self, url: str, html: str) -> Path:
        self.ensure()
        slug = self.slug_for_url(url)
        path = self.root / f"{slug}.html"
        path.write_text(html, encoding="utf-8")
        return path
