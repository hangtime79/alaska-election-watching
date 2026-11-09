"""Record when the state created a Dominion CVR export, from the file times in the export folder or zip.

Usage: python3 cvr_time.py PATH [LABEL]
  PATH  an extracted Dominion export folder or the original .zip
  LABEL optional note (e.g. "House+Senate rerun")
Appends a row to cvr_exports.csv (skips exact duplicates) and prints the export time.
Times are as stored in the zip (no time zone; most likely the state server's Alaska local time).
"""
import csv
import sys
import zipfile
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
LOG = HERE / "cvr_exports.csv"


def stamps(path: Path) -> dict[str, datetime]:
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as z:
            return {Path(i.filename).name: datetime(*i.date_time) for i in z.infolist() if not i.is_dir()}
    return {p.name: datetime.fromtimestamp(p.stat().st_mtime) for p in path.iterdir() if p.is_file()}


def main() -> None:
    path = Path(sys.argv[1])
    label = sys.argv[2] if len(sys.argv) > 2 else ""
    s = stamps(path)
    cvr = sorted(t for n, t in s.items() if n.startswith("CvrExport"))
    if not cvr:
        sys.exit(f"No CvrExport*.json files found in {path}")
    row = {
        "export_start": (s.get("Configuration.json") or cvr[0]).isoformat(sep=" "),
        "first_cvr_file": cvr[0].isoformat(sep=" "),
        "last_file": max(s.values()).isoformat(sep=" "),
        "cvr_files": len(cvr),
        "source": str(path),
        "label": label,
        "checked": datetime.now().isoformat(sep=" ", timespec="seconds"),
    }
    print(f"Export started {row['export_start']}  ({row['cvr_files']} CvrExport files, last file {row['last_file']})")
    rows = list(csv.DictReader(LOG.open())) if LOG.exists() else []
    if any(r["export_start"] == row["export_start"] and r["cvr_files"] == str(row["cvr_files"]) for r in rows):
        print("Same export as one already logged: no new data from the state.")
        return
    with LOG.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row))
        if not rows:
            w.writeheader()
        w.writerow(row)
    print(f"Logged to {LOG.name}")


if __name__ == "__main__":
    main()
