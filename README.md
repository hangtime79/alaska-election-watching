# Alaska election watching

Ballot-level analysis of Alaska's 2026 general election, built from the state's ranked-choice cast vote records (CVRs). The main question: does the claim that Sullivan Jr.'s and Heikes's votes belong to Sen. Dan Sullivan change who wins the US Senate race?

All tabulations are unofficial, from public data released by the Alaska Division of Elections. Every signed number is the Democratic side minus the Republican side: positive means Peltola (or Hill, Kreiss-Tomkins) ahead, negative means the Republican ahead.

## Pages

| File | What it shows |
|---|---|
| `page/senate_claims.html` | Alaska Senate count check: the claim, the count as it stands, how far name confusion could move it, and the projection. Self-contained; open in a browser. |
| `page/head.html` + `page/body.html` | The House forecast page, assembled by `build_page.py` |
| `page/vote_share_panels.html`, `page/city_shares_dem.html`, `page/city_shares_rep.html`, `page/beta_spray.html` | Supporting charts (data embedded in each file) |

## Data

The raw inputs are public. Download them into a folder and point `AK_DATA_DIR` at it (default `./data`):

- Dominion cast vote record exports for 2022, 2024 and 2026 from the [Alaska Division of Elections](https://www.elections.alaska.gov/), one folder per election (`alaska-2022`, `alaska-2024`, `alaska-2026`, `alaska-2022-special`).
- The 2026 precinct results file `GA_ENR_Precinct_State_of_Alaska.csv`.
- MEDSL and FEC files for the national incumbency and elasticity scripts go in `external/` (see each script's docstring).

Included here: the Senate CVR as tabulated by RCTab (`2026-11-05_00-56_rctab_cvr-senate.csv`), the Combined Ballot Report and Election Summary Report of 4 Nov 2026, and every derived JSON/CSV the pages read. SHA-256 checksums for the inputs are listed in the notes of `page/senate_claims.html`. The other large CVR tabulations are gitignored; rebuild them with RCTab.

## Reproducing

Scripts declare their dependencies inline; run them with [uv](https://docs.astral.sh/uv/).

1. Tabulate each contest with RCTab 2.1.0 ([BrightSpots/rcv](https://github.com/BrightSpots/rcv)) using the configs in `rctab-configs/` (paths are relative to the config: `../data/...`). Copy each `_rctab_cvr.csv` into the repository root.
2. Senate count check (`page/senate_claims.html`):
   - `uv run rcv.py 2026-11-05_00-56_rctab_cvr-senate.csv`: the ranked-choice rounds
   - `uv run rcv.py 2026-11-04_23-57_rctab_cvr.csv --snapshot 20241110` (and 20241112, 20241113, 20241114): the 2024 count over time
   - `uv run revised.py release_20261104_1309.json`: the count as it stands and the projection
   - `uv run senate_minor.py`: how each Senate first-choice group voted down the ticket
   - `uv run panels.py`: vote shares by area
   - `uv run --with pandas python claims/<script>.py`: the Sullivan Jr. and Heikes ranking sorts, confusion rates by ballot type and the Bush premium
   - `uv run --with pandas python claims/late_2024.py`: Peltola's 2024 late ballots against early-counted ones, by type and district (needs the 2024 count snapshots, the state's CVR exports of 10, 12, 13 and 14 Nov 2024 and the final, tabulated together into `2026-11-04_23-57_rctab_cvr.csv`)
3. House forecast: `uv run revised.py`, `uv run crossover.py`, `uv run flow_data.py`, then `python3 build_page.py`.
4. Check a page renders without sideways scrolling: `uv run --with playwright python page_check.py <page.html> out.png 1280` (and `400`). Run `playwright install chromium` first, or set `PW_CHROMIUM` to a browser binary.

Known gap: on the 2024 House final file, `rcv.py` puts about 2,000 more ballots in the final round than the official result. The cause has not been found.

## Contact

Grant Case - grant@aicriticalityindex.com
