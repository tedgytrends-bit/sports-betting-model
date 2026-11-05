"""Inspect provider response shapes; no secret or complete dataset is printed."""
import os, requests, statistics
session=requests.Session()
headers={"Authorization":"Bearer "+os.environ["CBBD_API_KEY"]}
for name,path,params in (
    ("roster","/teams/roster",{"season":2026}),
    ("players","/stats/player/season",{"season":2025}),
    ("transfers","/recruiting/portal",{"year":2025}),
    ("recruits","/recruiting/players",{"year":2025}),
):
    r=session.get("https://api.collegebasketballdata.com"+path,params=params,headers=headers,timeout=65)
    print(name,"status",r.status_code)
    r.raise_for_status()
    data=r.json()
    if not isinstance(data,list):
        print("response type",type(data).__name__)
        continue
    print("records",len(data))
    for x in data[:2]:
        print("sample",x)
    if name=="players":
        print("minutes quantiles")
        m=sorted(float(x["minutes"]) for x in data if x.get("minutes") is not None)
        print([m[min(len(m)-1,int(len(m)*z))] for z in (.1,.5,.9,.99)] if m else [])
