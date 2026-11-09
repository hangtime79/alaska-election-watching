# Screenshot the built page and report page errors and horizontal overflow.
# Usage: uv run --with playwright python page_check.py ballot-flow.html out.png WIDTH
import os, sys, asyncio
from playwright.async_api import async_playwright
async def main(src, out, width):
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=os.environ.get('PW_CHROMIUM') or None)  # set PW_CHROMIUM to use a specific browser binary
        pg = await b.new_page(viewport={'width': int(width), 'height': 1000}, device_scale_factor=1); pg.on('pageerror', lambda e: print('PAGE ERROR', e)); pg.on('console', lambda m: m.type=='error' and print('CONSOLE', m.text))
        html = open(src).read()
        html = '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body>' + html + '</body></html>'
        await pg.set_content(html, wait_until='networkidle')
        await pg.wait_for_timeout(800)
        await pg.screenshot(path=out, full_page=True)
        w = await pg.evaluate('document.documentElement.scrollWidth')
        print(out, 'scrollWidth', w)
        await b.close()
asyncio.run(main(*sys.argv[1:4]))
