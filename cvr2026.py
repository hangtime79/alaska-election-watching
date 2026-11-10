"""The 2026 CVR files every script reads. Change these when a new export lands.

Current: the 9 Nov 2026 export (started 15:03 Alaska time, 210,944 ballots), tabulated with
rctab-configs/alaska-2026-1109-*.json. The 4 Nov export (204,530 ballots) is in the files named
2026-11-04_23-33_rctab_cvr.csv, 2026-11-05_00-56_rctab_cvr-senate.csv, 2026-11-05_14-36_rctab_cvr-2026-governor.csv.
"""
EXPORT = "9 Nov"
HOUSE = "2026-11-10_14-13_rctab_cvr-2026-1109-house.csv"
SENATE = "2026-11-10_14-13_rctab_cvr-2026-1109-senate.csv"
GOVERNOR = "2026-11-10_14-13_rctab_cvr-2026-1109-governor.csv"
DOMINION = "alaska-2026-1109"          # folder under AK_DATA_DIR
