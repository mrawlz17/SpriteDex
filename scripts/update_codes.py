#!/usr/bin/env python3
"""SpriteDex Fortnite Admin Panel/Lobby Hack code watcher.

Primary source: Fortnite.GG Lobby Hacks.
Corroboration: NerdsChalk + AllThings.How.
Reddit is not required because GitHub Actions runners are commonly blocked (403).

Safety:
- One Fortnite.GG-only discovery may surface as Unverified.
- Two independent sources are required for Confirmed.
- Confirmed codes are never downgraded just because a source is stale/offline.
- Codes are never deleted merely because they disappear from a page.
- Two explicit independent expiry reports are required for Expired.
- Fewer than two reachable endpoints is a successful safe no-op.
"""
from __future__ import annotations
import html,json,re,sys
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
import requests
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
DATA_FILE=ROOT/"codes.json"

SOURCES=[
 ("site:fortnitegg","https://fortnite.gg/lobby-hacks","fortnitegg"),
 ("site:nerdschalk","https://nerdschalk.com/fortnite-admin-panel-codes/","working_article"),
 ("site:allthingshow","https://allthings.how/fortnite-admin-panel-codes/","working_article"),
 ("site:allthingshow-bush","https://allthings.how/fortnite-how-to-get-the-bush-sprite-cheat-master-variant-included/","bush_article"),
]
PRIMARY_SOURCE="site:fortnitegg"
SINGLE_SOURCE_DISCOVERY_ALLOWLIST={PRIMARY_SOURCE}
HEADERS={"User-Agent":"Mozilla/5.0 (compatible; SpriteDexCodeBot/3.1; +https://github.com/mrawlz17/SpriteDex)"}
STOPWORDS={"FORTNITE","OVERRIDE","CHAPTER","SEASON","SPRITE","SPRITES","MASTER","CHEAT","LOBBY","HACK","HACKS","CODES","CODE","ADMIN","PANEL","REWARD","REWARDS","LOADING","SCREEN","SCREENS","CURRENT","KNOWN","WORKING","AVAILABLE","ACTIVE","EXPIRED","DISABLED","CONSUMABLE","RESOURCES","LOCKER","ITEMS"}
LEGACY_SOURCE_MAP={"reddit-o2-thread":"reddit-post:1vo4bwf","reddit-all-known":"reddit-post:1vth12e","reddit-19-codes":"reddit-post:1vtj0yi","nerdschalk":"site:nerdschalk"}

def norm(v:str)->str:return re.sub(r"[^A-Za-z0-9]","",v).upper()

def looks_like_code(v:str)->bool:
    v=v.strip()
    if not re.fullmatch(r"[A-Za-z0-9]{5,24}",v):return False
    n=norm(v)
    return n not in STOPWORDS and any(c.isalpha() for c in n)

def fetch(url):
    r=requests.get(url,headers=HEADERS,timeout=35);r.raise_for_status();return r

def canonical_sources(values):
    out=set()
    for v in values or []:
        v=LEGACY_SOURCE_MAP.get(str(v),str(v))
        if v.startswith("reddit-search:"):continue
        if v:out.add(v)
    return out

def clean_reward(v):
    v=html.unescape(v)
    v=re.sub(r"\bNEW\b","",v,flags=re.I)
    v=re.sub(r"https?://\S+","",v)
    v=re.sub(r"^[\s\-–—:=>|()[\]*`]+|[\s\-–—:=>|()[\]*`]+$","",v)
    v=re.sub(r"\s+"," ",v).strip()
    return v if v and len(v)<=150 else None

def infer_category(reward,section=""):
    r=reward.lower();s=section.lower()
    if "sprite" in r or "sprite" in s:return "Cheat Master Sprite"
    if re.search(r"\bxp\b",r):return "XP"
    if "sprite dust" in r or " dust" in r:return "Sprite Dust"
    if "loading screen" in r or "loading" in s:return "Loading Screen"
    if "tetrimino" in r or "tetris" in r or "fun effect" in s:return "Lobby Effect"
    if any(x in r for x in ("extractor","accelerator","locator","taco","supply drop")):return "Gizmo"
    return "Unknown"

def scan_fortnitegg(text):
    soup=BeautifulSoup(text,"html.parser")
    lines=[html.unescape(x).strip() for x in soup.stripped_strings if x.strip()]
    heads={"Sprites":"Sprites","Loading Screens & Locker Items":"Loading Screens & Locker Items","Consumable Resources":"Consumable Resources","Fun Effects":"Fun Effects"}
    active={};section=None;i=0
    while i<len(lines):
        line=lines[i]
        if line in heads:section=heads[line];i+=1;continue
        if section and looks_like_code(line):
            reward=lines[i+1] if i+1<len(lines) else ""
            if reward not in heads and not looks_like_code(reward):
                reward=clean_reward(reward)
                if reward:
                    active[norm(line)]={"display":line,"reward":reward,"category":infer_category(reward,section)}
                    i+=2;continue
        i+=1
    return active,set()

def code_section(tag):
    h=tag.find_previous("h2")
    return h.get_text(" ",strip=True).lower() if h else ""

def code_reward(tag,display):
    if tag.parent is None:return None
    text=" ".join(tag.parent.stripped_strings)
    text=re.sub(re.escape(display),"",text,count=1,flags=re.I)
    text=re.sub(r"^[\s\-–—:]+","",text).strip()
    return clean_reward(text)

def scan_working_article(text):
    soup=BeautifulSoup(text,"html.parser");active={};expired=set()
    for tag in soup.find_all("code"):
        display=tag.get_text(" ",strip=True)
        if not looks_like_code(display):continue
        section=code_section(tag)
        if "expired" in section:expired.add(norm(display));continue
        if "working" not in section:continue
        reward=code_reward(tag,display)
        if reward:active[norm(display)]={"display":display,"reward":reward,"category":infer_category(reward)}
    return active,expired

def scan_bush_article(text):
    plain=" ".join(BeautifulSoup(text,"html.parser").stripped_strings)
    if re.search(r"\bGatherAndCraft\b",plain,re.I) and re.search(r"Cheat Master.*Bush|Bush.*Cheat Master",plain,re.I):
        return {"GATHERANDCRAFT":{"display":"GatherAndCraft","reward":"Cheat Master Bush Sprite (Requires Wrixel/Ziggy story quest)","category":"Cheat Master Sprite"}},set()
    return {},set()

def reward_key(v):return re.sub(r"[^a-z0-9]+"," ",v.lower()).strip()

def best_display(displays,code):
    c=displays.get(code,[])
    return sorted(c,key=lambda x:x[0])[0][1] if c else code

def best_reward(rewards,code):
    best=None
    for e in rewards.get(code,{}).values():
        score=len(e["sources"])
        if best is None or score>best[0]:best=(score,e["text"],e["category"])
    return (best[1],best[2]) if best and best[0]>=2 else (None,"Unknown")

def main():
    current=json.loads(DATA_FILE.read_text(encoding="utf-8"))
    existing={norm(x["code"]):x for x in current.get("codes",[])}
    sightings=defaultdict(set);exp=defaultdict(set);displays=defaultdict(list)
    rewards=defaultdict(lambda:defaultdict(lambda:{"sources":set(),"text":"","category":"Unknown"}))
    successful=0

    for priority,(sid,url,kind) in enumerate(SOURCES):
        try:
            r=fetch(url);successful+=1
            if kind=="fortnitegg":active,expired=scan_fortnitegg(r.text)
            elif kind=="working_article":active,expired=scan_working_article(r.text)
            else:active,expired=scan_bush_article(r.text)
            for code,info in active.items():
                sightings[code].add(sid);displays[code].append((priority,info["display"]))
                k=reward_key(info["reward"])
                rewards[code][k]["sources"].add(sid);rewards[code][k]["text"]=info["reward"];rewards[code][k]["category"]=info["category"]
            for code in expired:exp[code].add(sid)
            print(f"{sid}: {len(active)} active, {len(expired)} expired candidates")
        except Exception as exc:
            print(f"Warning: {sid} failed: {exc}",file=sys.stderr)

    if successful<2:
        print("Safe no-op: fewer than two code sources reachable; codes.json unchanged.",file=sys.stderr);return 0

    now=datetime.now(timezone.utc);today=now.date().isoformat();changed=False

    for code,item in existing.items():
        hist=canonical_sources(item.get("observedSources"))|sightings.get(code,set())|exp.get(code,set())
        if item.get("observedSources")!=sorted(hist):item["observedSources"]=sorted(hist);changed=True
        if item.get("sourceCount")!=len(hist):item["sourceCount"]=len(hist);changed=True
        if sightings.get(code) or exp.get(code):
            if item.get("lastSeen")!=today:item["lastSeen"]=today;changed=True

        display=best_display(displays,code)
        if code in displays and item.get("code")!=display:item["code"]=display;changed=True
        if item.get("status")!="confirmed" and len(hist)>=2:item["status"]="confirmed";changed=True

        exp_hist=canonical_sources(item.get("expiredSources"))|exp.get(code,set())
        if item.get("expiredSources")!=sorted(exp_hist):item["expiredSources"]=sorted(exp_hist);changed=True
        if len(exp_hist)>=2 and item.get("availability")!="expired":item["availability"]="expired";changed=True
        elif "availability" not in item:item["availability"]="active";changed=True

        if not item.get("reward") or item.get("reward")=="Reward not yet identified":
            reward,cat=best_reward(rewards,code)
            if reward:item["reward"]=reward;item["category"]=cat;changed=True

    for code in sorted(set(sightings)|set(exp)):
        if code in existing:continue
        sources=sightings.get(code,set())|exp.get(code,set())
        if len(sources)<2 and not (sources&SINGLE_SOURCE_DISCOVERY_ALLOWLIST):
            print(f"Ignoring one-source fallback candidate {code} from {sorted(sources)}");continue

        display=best_display(displays,code);reward,cat=best_reward(rewards,code)
        if reward is None and PRIMARY_SOURCE in sightings.get(code,set()):
            for e in rewards.get(code,{}).values():
                if PRIMARY_SOURCE in e["sources"]:reward=e["text"];cat=e["category"];break
        reward=reward or "Reward not yet identified"
        if cat=="Unknown":cat=infer_category(reward)

        item={"id":code,"code":display,"reward":reward,"category":cat,
              "status":"confirmed" if len(sources)>=2 else "unverified",
              "firstSeen":today,"lastSeen":today,
              "availability":"expired" if len(exp.get(code,set()))>=2 else "active",
              "observedSources":sorted(sources),"sourceCount":len(sources)}
        if exp.get(code):item["expiredSources"]=sorted(exp[code])
        current.setdefault("codes",[]).append(item);existing[code]=item;changed=True
        print(f"New code: {display} ({item['status']})")

    urls=[u for _,u,_ in SOURCES]
    if current.get("sources")!=urls:current["sources"]=urls;changed=True

    if not changed:
        print(f"No code database changes. {len(current.get('codes',[]))} codes.");return 0

    current["databaseVersion"]=now.strftime("%Y.%m.%d.%H%M")
    current["updated"]=now.isoformat().replace("+00:00","Z")
    DATA_FILE.write_text(json.dumps(current,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(f"Updated code database: {len(current.get('codes',[]))} codes.")
    return 0

if __name__=="__main__":raise SystemExit(main())
