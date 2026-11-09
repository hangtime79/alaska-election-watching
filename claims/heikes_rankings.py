# Run from the repo root: uv run --with pandas python claims/<script>.py
import sys; sys.path.insert(0,'.')
import pandas as pd, collections
import senate_minor as sm
s=pd.read_csv(sm.SEN,dtype=str,keep_default_na=False)
S={"Sullivan":"Sullivan","Peltola":"Peltola","Heikes":"Heikes","Sullivan Jr.":"Jr","Write-in":"WI"}
def seq(row):
    out=[]
    for v in row:
        if v=="undervote": out.append("_"); continue
        if "\n" in v:
            out.append("OV(" + "+".join(S.get(sm.SHORT.get(n,n),n) for n in v.split("\n")) + ")"); continue
        out.append(S.get(sm.SHORT.get(v,v),v))
    while out and out[-1]=="_": out.pop()
    return out
c=collections.Counter(); raw=collections.Counter()
for r in s[sm.RANKS].itertuples(index=False):
    q=seq(r)
    nz=[x for x in q if x!="_"]
    if not nz or nz[0]!="Heikes": continue
    raw[" > ".join(q)]+=1
    # collapse: drop blanks and repeats
    col=[]
    for x in nz:
        if x not in col: col.append(x)
    c[" > ".join(col)]+=1
print("TOTAL",sum(c.values()))
for k,v in c.most_common(): print(f"{v:6,}  {k}")
print("\nraw (with blanks/repeats), top 40")
for k,v in raw.most_common(40): print(f"{v:6,}  {k}")
print("distinct raw",len(raw))

print("\n===== grouped")
g=collections.Counter()
for k,v in c.items():
    q=k.split(" > ")
    has_ov=any(x.startswith("OV") for x in q)
    fin=None
    for x in q[1:]:
        if x.startswith("OV"): fin="overvote"; break
        if x in("Sullivan","Peltola"): fin=x; break
    fin=fin or "stops"
    sul="Sullivan" in q; jr="Jr" in q; pel="Peltola" in q
    ijr=q.index("Jr") if jr else 99; ipel=q.index("Peltola") if pel else 99
    if fin=="overvote": key="overvote"
    elif sul: key=f"{fin}; ranks Sullivan"
    elif jr and ijr<ipel: key=f"{fin}; Jr ranked, no Sullivan, Jr above Peltola"
    elif jr: key=f"{fin}; Jr ranked, no Sullivan, Jr below Peltola"
    else: key=f"{fin}; neither Sullivan ranked"
    g[key]+=v
for k,v in sorted(g.items()): print(f"{v:6,}  {k}")

print("\n===== by group")
gg=collections.defaultdict(list)
for k,v in c.items():
    q=k.split(" > ")
    fin=None
    for x in q[1:]:
        if x.startswith("OV"): fin="overvote"; break
        if x in("Sullivan","Peltola"): fin=x; break
    fin=fin or "stops"
    sul="Sullivan" in q; jr="Jr" in q; pel="Peltola" in q
    ijr=q.index("Jr") if jr else 99; ipel=q.index("Peltola") if pel else 99
    if fin=="overvote": key="overvote"
    elif sul: key=f"{fin}; ranks Sullivan"
    elif jr and ijr<ipel: key=f"{fin}; Jr above Peltola, no Sullivan"
    elif jr: key=f"{fin}; Jr below Peltola, no Sullivan"
    else: key=f"{fin}; neither Sullivan"
    gg[key].append((v,k))
for key in gg:
    print("\n##",key,sum(v for v,_ in gg[key]))
    for v,k in sorted(gg[key],reverse=True): print(f"   {v:5,}  {k}")
