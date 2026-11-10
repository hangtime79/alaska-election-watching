"""Wrap the count-check pages in full HTML documents for GitHub Pages.

page/senate_claims.html -> docs/index.html        (Senate count check)
page/house_check.html   -> docs/house/index.html  (House count check)

The page sources are written for the claude.ai artifact viewer, which adds the document skeleton.
Run after editing a page: python3 build_site.py
Before publishing a new version, archive the live one first:
  python3 build_site.py --archive-senate 2026-11-10 --archive-house 2026-11-10
copies the current docs/index.html to docs/archive/<date>/ and docs/house/index.html to docs/archive/<date>/house/,
with a banner pointing to the current page. Then add the new walk to each page's "What changed" section and link the
archived copy there.
"""
import argparse
from pathlib import Path

HERE = Path(__file__).parent
PAGES = {"senate_claims.html": "docs/index.html", "house_check.html": "docs/house/index.html"}
HEAD = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
        '<style>:root{color-scheme:light}body{margin:0;font:14px system-ui,sans-serif}img{max-width:100%}[hidden]{display:none!important}</style>'
        '</head><body>')
BASE = "https://hangtime79.github.io/alaska-election-watching/"
ap = argparse.ArgumentParser()
ap.add_argument("--archive-senate"); ap.add_argument("--archive-house")
args = ap.parse_args()
for label, src, sub, name in ((args.archive_senate, "docs/index.html", "", "Senate"), (args.archive_house, "docs/house/index.html", "house/", "House")):
    if not label:
        continue
    out = HERE / "docs" / "archive" / label / sub / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    banner = (f'<div style="background:#fbe9c8;color:#2e2b28;border-bottom:2px solid #c25a22;padding:10px 16px;font:600 15px system-ui,sans-serif;text-align:center">'
              f'Archived: {name} count check, version of {label}. These numbers have been superseded. <a href="{BASE}{sub}" style="color:#244e78">Read the current version</a>.</div>')
    out.write_text((HERE / src).read_text().replace("<body>", "<body>" + banner, 1))
    print("archived", out)
for src, dst in PAGES.items():
    body = (HERE / "page" / src).read_text()
    out = HERE / dst
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(HEAD + body + '</body></html>\n')
    print("wrote", out)
(HERE / "docs" / ".nojekyll").write_text("")
