# Run from the repo root: uv run --with pandas python claims/<script>.py
import json, sys
sys.path.insert(0, '.')
import cross_race as cr
m = cr.load()
R = json.load(open('report_projection.json'))
tgt='SF'
for vt,g in m.groupby('vt'):
    print(vt, len(g), 'net/ballot', round(g[tgt+'_net'].mean(),4), 'two/ballot', round(g[tgt+'_two'].mean(),4), 'net', int(g[tgt+'_net'].sum()))
print('all', round(m[tgt+'_net'].mean(),4), round(m[tgt+'_two'].mean(),4))
