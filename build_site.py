"""Wrap the count-check pages in full HTML documents for GitHub Pages.

page/senate_claims.html -> docs/index.html        (Senate count check)
page/house_check.html   -> docs/house/index.html  (House count check)

The page sources are written for the claude.ai artifact viewer, which adds the document skeleton.
Run after editing a page: python3 build_site.py
"""
from pathlib import Path

HERE = Path(__file__).parent
PAGES = {"senate_claims.html": "docs/index.html", "house_check.html": "docs/house/index.html"}
HEAD = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
        '<style>:root{color-scheme:light}body{margin:0;font:14px system-ui,sans-serif}img{max-width:100%}[hidden]{display:none!important}</style>'
        '</head><body>')
for src, dst in PAGES.items():
    body = (HERE / "page" / src).read_text()
    out = HERE / dst
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(HEAD + body + '</body></html>\n')
    print("wrote", out)
(HERE / "docs" / ".nojekyll").write_text("")
