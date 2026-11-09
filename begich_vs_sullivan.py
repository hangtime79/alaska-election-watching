# Begich against Sullivan on the same 2026 ballots, first choices, with the legislative baseline taken over exactly the same voters.
# Usage: uv run --with pandas python begich_vs_sullivan.py   (needs legislative_2026.csv from legislative.py and crossover_2026.csv)
import pandas as pd
W = '/opt/github/election-watching/'
L = pd.read_csv(W + 'legislative_2026.csv', dtype=str)
L = L[(L.clean == 'True') & L.leg_first.isin(['D', 'R'])]
x = pd.read_csv(W + 'crossover_2026.csv', dtype=str, keep_default_na=False)
m = L.merge(x[['RCTab CVR Id', 'H1', 'S1']], on='RCTab CVR Id')
def mg(d, r):
    return (d - r) / (d + r) * 100
lm = mg((m.leg_first == 'D').sum(), (m.leg_first == 'R').sum())
rows = [
  ('House: Hill + Hafner − Begich', m.H1.isin(['Hill', 'Hafner']).sum(), (m.H1 == 'Begich').sum()),
  ('House: Hill − Begich', (m.H1 == 'Hill').sum(), (m.H1 == 'Begich').sum()),
  ('Senate: Peltola − Sullivan', (m.S1 == 'Peltola').sum(), (m.S1 == 'Sullivan').sum()),
  ('Senate: Peltola − (Sullivan + Heikes + Sullivan Jr.)', (m.S1 == 'Peltola').sum(), m.S1.isin(['Sullivan', 'Heikes', 'Sullivan Jr.']).sum()),
]
print(f'clean-contest ballots {len(m):,}; legislative margin {lm:+.2f}')
for name, d, r in rows:
    rm = mg(d, r)
    print(f'  {name:55} D {d:>7,} R {r:>7,}  margin {rm:+.2f}  pair effect {rm:+.2f} − ({lm:+.2f}) == {rm - lm:+.2f}')
print('\nSame voters on both sides of the comparison:')
specs = [('House: Hill + Hafner − Begich', m.H1, ['Hill', 'Hafner'], ['Begich']),
         ('House: Hill + Hafner − (Begich + McDermott)', m.H1, ['Hill', 'Hafner'], ['Begich', 'McDermott']),
         ('Senate: Peltola − Sullivan', m.S1, ['Peltola'], ['Sullivan']),
         ('Senate: Peltola − (Sullivan + Heikes + Sullivan Jr.)', m.S1, ['Peltola'], ['Sullivan', 'Heikes', 'Sullivan Jr.'])]
for name, col, D, R in specs:
    sub = m[col.isin(D + R)]
    d, r = col[col.isin(D)].count(), col[col.isin(R)].count()
    rm = mg(d, r); l = mg((sub.leg_first == 'D').sum(), (sub.leg_first == 'R').sum())
    print(f'  {name:55} ballots {len(sub):>6,}  race {rm:+6.2f}  legislative (same ballots) {l:+6.2f}  pair {rm:+.2f} − ({l:+.2f}) == {rm - l:+.2f}')
