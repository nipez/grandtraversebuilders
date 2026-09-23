#!/usr/bin/env python3
"""Generate search-index.json from the businesses array embedded in index.html.

index.html already contains the full directory as `const businesses=[...]` with
name (n), phone (p), address (a), website (w), categories (c), and slug (s).
Reuse it as the single source of truth so the search index never drifts from
the directory. Re-run whenever directory data changes:

    python3 scripts/build_search_index.py
"""
from __future__ import annotations

import json
import re
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
CITY_RE = re.compile(r",\s*([A-Za-z .'\-]+),\s*MI\b", re.I)


def extract_array(text: str, var: str = "businesses") -> str:
    start = text.index(f"const {var}=")
    i = text.index("[", start)
    depth = 0
    for j in range(i, len(text)):
        ch = text[j]
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return text[i : j + 1]
    raise ValueError(f"unterminated {var} array")


def city_of(address: str) -> str:
    if not address:
        return ""
    m = CITY_RE.search(address)
    return m.group(1).strip() if m else ""


def main() -> None:
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    businesses = json.loads(extract_array(html))
    index = []
    for b in businesses:
        index.append(
            {
                "n": b.get("n", ""),
                "s": b.get("s", ""),
                "c": b.get("c", []) or [],
                "city": city_of(b.get("a", "") or ""),
                "a": b.get("a", "") or "",
                "p": b.get("p", "") or "",
            }
        )
    index.sort(key=lambda x: x["n"].lower())
    out = ROOT / "search-index.json"
    out.write_text(
        json.dumps(index, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    cats = sorted({c for b in index for c in b["c"]})
    cities = sorted({b["city"] for b in index if b["city"]})
    print(
        f"Wrote {out.name}: {len(index)} businesses, "
        f"{len(cats)} trades, {len(cities)} cities"
    )


if __name__ == "__main__":
    main()
