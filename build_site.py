"""Wrap page/senate_claims.html in a full HTML document for GitHub Pages (docs/index.html).

The page source is written for the claude.ai artifact viewer, which adds the document skeleton.
Run after editing the page: python3 build_site.py
"""
from pathlib import Path

HERE = Path(__file__).parent
body = (HERE / "page" / "senate_claims.html").read_text()
html = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
        '<style>:root{color-scheme:light}body{margin:0;font:14px system-ui,sans-serif}img{max-width:100%}[hidden]{display:none!important}</style>'
        '</head><body>' + body + '</body></html>\n')
out = HERE / "docs" / "index.html"
out.parent.mkdir(exist_ok=True)
out.write_text(html)
(HERE / "docs" / ".nojekyll").write_text("")
print("wrote", out)
