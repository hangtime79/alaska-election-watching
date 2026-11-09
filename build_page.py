"""Assemble the published Sankey/projection page from page/ templates and the JSON outputs.

Usage: python3 build_page.py [OUT_HTML]   (default: ballot-flow.html)
Run flow_data.py, project.py, report_projection.py and revised.py first. Then publish OUT_HTML to
a published page.
"""
import sys
from pathlib import Path

HERE = Path(__file__).parent
out = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "ballot-flow.html"
body = (HERE / "page/body.html").read_text()
for token, f in [("__DATA__", "flow.json"), ("__PROJ__", "projection.json"), ("__REP__", "report_projection.json"), ("__XOVER__", "crossover.json"), ("__REV__", "revised_projection.json")]:
    body = body.replace(token, (HERE / f).read_text())
out.write_text((HERE / "page/head.html").read_text() + body)
print(f"wrote {out}")
