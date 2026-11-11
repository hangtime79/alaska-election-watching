"""The 2026 CVR files every script reads. Change these when a new export lands.

Current: the 10 Nov 2026 export (started 18:55 Alaska time), tabulated with rctab-configs/alaska-2026-1110-*.json.
The 9 Nov export (210,944 ballots) is in 2026-11-10_14-13_rctab_cvr-2026-1109-*.csv. The 4 Nov export (204,530 ballots) is in the files named
2026-11-04_23-33_rctab_cvr.csv, 2026-11-05_00-56_rctab_cvr-senate.csv, 2026-11-05_14-36_rctab_cvr-2026-governor.csv.
"""
EXPORT = "10 Nov"
HOUSE = "2026-11-10_23-45_rctab_cvr-2026-1110-house.csv"
SENATE = "2026-11-10_23-45_rctab_cvr-2026-1110-senate.csv"
GOVERNOR = "2026-11-10_23-45_rctab_cvr-2026-1110-governor.csv"
DOMINION = "alaska-2026-1110"          # folder under AK_DATA_DIR
