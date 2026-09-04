import sqlite3
import requests
import statistics
from datetime import datetime, timezone

from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.metrics import dp

DB_NAME = "dexro_app.db"
API_KEY = "YOUR_API_KEY_HERE"

def get_db():
    return sqlite3.connect(DB_NAME)

def setup_database():
    db = get_db()
    cur = db.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS research (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, question TEXT,
        keyword TEXT, created_at TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS videos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, research_id INTEGER,
        youtube_id TEXT, title TEXT, channel TEXT, published_at TEXT,
        views INTEGER, likes INTEGER, comments INTEGER,
        engagement REAL, views_per_day REAL)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS opportunities (
        id INTEGER PRIMARY KEY AUTOINCREMENT, research_id INTEGER,
        opportunity_type TEXT, title TEXT, description TEXT, evidence TEXT,
        potential TEXT, confidence TEXT, priority TEXT,
        suggested_action TEXT, status TEXT, created_at TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS ideas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, research_id INTEGER,
        opportunity_id INTEGER, title TEXT, angle TEXT, audience TEXT,
        format TEXT, evidence TEXT, score INTEGER, status TEXT,
        created_at TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS opportunity_validation (
        id INTEGER PRIMARY KEY AUTOINCREMENT, research_id INTEGER,
        demand_score REAL, demand_level TEXT, demand_evidence TEXT,
        hype_score REAL, hype_level TEXT, hype_evidence TEXT,
        competition_score REAL, competition_level TEXT,
        competition_evidence TEXT, performance_score REAL,
        velocity_score REAL, opportunity_score REAL,
        opportunity_level TEXT, decision TEXT, decision_reason TEXT,
        created_at TEXT)""")
    db.commit()
    db.close()

def format_number(number):
    try: number = float(number)
    except: return "0"
    if number >= 1_000_000: return f"{number/1_000_000:.2f}M"
    if number >= 1_000: return f"{number/1_000:.1f}K"
    return str(int(number))

def short_title(title, length=48):
    return title if len(title) <= length else title[:length] + "..."

def clamp(value, minimum=0, maximum=100):
    return max(minimum, min(maximum, value))

def add_label(parent, text, size=17, height=50):
    label = Label(text=text, font_size=size, size_hint_y=None,
                  height=dp(height), halign="left", valign="middle")
    label.bind(size=lambda inst, value: setattr(inst, "text_size", value))
    parent.add_widget(label)
    return label

def youtube_search(keyword, max_results=10):
    if API_KEY == "YOUR_API_KEY_HERE":
        raise Exception("YouTube API key is missing. Add your NEW API key.")
    r = requests.get("https://www.googleapis.com/youtube/v3/search",
        params={"part":"snippet","q":keyword,"type":"video",
                "maxResults":max_results,"key":API_KEY}, timeout=20)
    if r.status_code != 200: raise Exception("YouTube Search Error:\n"+r.text)
    results = []
    for item in r.json().get("items", []):
        if "videoId" not in item.get("id", {}): continue
        s = item["snippet"]
        results.append({"youtube_id":item["id"]["videoId"],
                        "title":s["title"], "channel":s["channelTitle"],
                        "published_at":s["publishedAt"]})
    return results

def get_statistics(video_ids):
    if not video_ids: return {}
    r = requests.get("https://www.googleapis.com/youtube/v3/videos",
        params={"part":"statistics","id":",".join(video_ids),"key":API_KEY},
        timeout=20)
    if r.status_code != 200: raise Exception("YouTube Statistics Error:\n"+r.text)
    stats = {}
    for item in r.json().get("items", []):
        s = item.get("statistics", {})
        stats[item["id"]] = {"views":int(s.get("viewCount",0)),
                             "likes":int(s.get("likeCount",0)),
                             "comments":int(s.get("commentCount",0))}
    return stats

def calculate_metrics(results, stats):
    final, now = [], datetime.now(timezone.utc)
    for video in results:
        vid = video["youtube_id"]; s = stats.get(vid,{})
        views, likes, comments = s.get("views",0),s.get("likes",0),s.get("comments",0)
        engagement = ((likes+comments)/views*100) if views else 0
        try:
            published = datetime.fromisoformat(video["published_at"].replace("Z","+00:00"))
            days = max((now-published).total_seconds()/86400, 1)
            velocity = views/days
        except: velocity = 0
        final.append({**video,"views":views,"likes":likes,"comments":comments,
                      "engagement":engagement,"views_per_day":velocity})
    return sorted(final,key=lambda x:x["views"],reverse=True)

def save_research(name, question, keyword, videos):
    db=get_db(); cur=db.cursor()
    cur.execute("INSERT INTO research(name,question,keyword,created_at) VALUES(?,?,?,?)",
                (name,question,keyword,datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    rid=cur.lastrowid
    for v in videos:
        cur.execute("""INSERT INTO videos
        (research_id,youtube_id,title,channel,published_at,views,likes,comments,engagement,views_per_day)
        VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (rid,v["youtube_id"],v["title"],v["channel"],v["published_at"],v["views"],
         v["likes"],v["comments"],v["engagement"],v["views_per_day"]))
    db.commit(); db.close(); return rid

def get_history():
    db=get_db(); rows=db.execute(
        "SELECT id,name,question,keyword,created_at FROM research ORDER BY id DESC").fetchall()
    db.close(); return rows

def get_research_videos(rid):
    db=get_db(); rows=db.execute("""SELECT youtube_id,title,channel,published_at,
        views,likes,comments,engagement,views_per_day FROM videos
        WHERE research_id=? ORDER BY views DESC""",(rid,)).fetchall()
    db.close()
    return [dict(zip(["youtube_id","title","channel","published_at","views","likes",
                      "comments","engagement","views_per_day"],r)) for r in rows]

def generate_opportunities(rid,videos):
    if not videos:return []
    views=[v["views"] for v in videos]; eng=[v["engagement"] for v in videos]
    vel=[v["views_per_day"] for v in videos]
    av=statistics.mean(views); med=statistics.median(views)
    ae=statistics.mean(eng); al=statistics.mean(vel)
    tv=max(videos,key=lambda x:x["views"])
    te=max(videos,key=lambda x:x["engagement"])
    tvl=max(videos,key=lambda x:x["views_per_day"])
    ops=[]
    if med>0 and tv["views"]/med>=2:
        ops.append(("Performance","High-performing content signal",
                    "One or more videos significantly outperform the sample median.",
                    f"Top video has {format_number(tv['views'])} views vs median {format_number(med)}.",
                    "HIGH","MEDIUM","HIGH","MAKE"))
    if ae>0 and te["engagement"]>=ae*1.5:
        ops.append(("Engagement","Strong engagement signal",
                    "A video is generating substantially higher engagement than the sample average.",
                    f"Best engagement: {te['engagement']:.2f}% vs average {ae:.2f}%.",
                    "HIGH","MEDIUM","HIGH","TEST"))
    if al>0 and tvl["views_per_day"]>=al*1.5:
        ops.append(("Velocity","High view-velocity signal",
                    "A video is accumulating views/day faster than the sample average.",
                    f"Best velocity: {format_number(tvl['views_per_day'])} views/day vs average {format_number(al)}.",
                    "HIGH","MEDIUM","HIGH","TEST"))
    if len(videos)<10:
        ops.append(("Research","Sample size is limited",
                    "More evidence could improve decision confidence.",
                    f"Only {len(videos)} videos are currently in the saved dataset.",
                    "MEDIUM","HIGH","MEDIUM","RESEARCH MORE"))
    if not ops:
        ops.append(("Research","No strong opportunity detected yet",
                    "The current dataset does not show a strong enough signal.",
                    f"{len(videos)} videos analyzed.","MEDIUM","LOW","MEDIUM","RESEARCH MORE"))
    db=get_db(); cur=db.cursor()
    cur.execute("DELETE FROM opportunities WHERE research_id=?",(rid,))
    for o in ops:
        cur.execute("""INSERT INTO opportunities
        (research_id,opportunity_type,title,description,evidence,potential,confidence,priority,
         suggested_action,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
         (rid,*o,"OPEN",datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    db.commit(); db.close()
    return ops

def get_opportunities(rid):
    db=get_db()
    rows=db.execute("""SELECT id,opportunity_type,title,description,evidence,potential,
        confidence,priority,suggested_action,status FROM opportunities WHERE research_id=?
        ORDER BY CASE priority WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END""",(rid,)).fetchall()
    db.close()
    keys=["id","type","title","description","evidence","potential","confidence","priority","action","status"]
    return [dict(zip(keys,r)) for r in rows]

def calculate_demand(v):
    if len(v)<3:return {"score":0,"level":"UNKNOWN","evidence":"At least 3 videos are required."}
    views=[max(x["views"],0) for x in v]; eng=[max(x["engagement"],0) for x in v]; top=max(views)
    if top<=0:return {"score":0,"level":"UNKNOWN","evidence":"No usable view data."}
    mr=clamp(statistics.median(views)/top*100); ar=clamp(statistics.mean(views)/top*100)
    er=clamp(statistics.mean(eng)/max(eng)*100) if max(eng)>0 else 0
    score=round(clamp(mr*.5+ar*.3+er*.2),1)
    level="HIGH" if score>=70 else "MEDIUM" if score>=45 else "LOW"
    return {"score":score,"level":level,"evidence":f"Demand proxy {score}/100; median views {mr:.0f}% and average views {ar:.0f}% of top video. Not search volume."}

def calculate_hype(v):
    dated=[]
    for x in v:
        try: dated.append((datetime.fromisoformat(x["published_at"].replace("Z","+00:00")),x))
        except: pass
    if len(dated)<6:return {"score":0,"level":"UNKNOWN","evidence":"At least 6 dated videos are required."}
    dated.sort(reverse=True); m=len(dated)//2; recent=dated[:m]; old=dated[m:]
    rv=[x[1]["views_per_day"] for x in recent if x[1]["views_per_day"]>0]
    ov=[x[1]["views_per_day"] for x in old if x[1]["views_per_day"]>0]
    if not rv or not ov or statistics.median(ov)<=0:return {"score":0,"level":"UNKNOWN","evidence":"Insufficient velocity data."}
    r,o=statistics.median(rv),statistics.median(ov); change=(r-o)/o*100
    score=round(clamp(50+change*.8),1)
    level="RISING" if change>=25 else "FALLING" if change<=-20 else "STABLE"
    return {"score":score,"level":level,"evidence":f"Recent median {format_number(r)} views/day vs older {format_number(o)}; change {change:+.1f}%."}

def calculate_competition(v):
    if len(v)<3:return {"score":0,"level":"UNKNOWN","evidence":"At least 3 videos are required."}
    channels=[x["channel"] for x in v if x["channel"]]; unique=len(set(channels)); n=len(v)
    total=sum(max(x["views"],0) for x in v)
    top3=sum(sorted([max(x["views"],0) for x in v],reverse=True)[:3])
    share=top3/total if total else 1
    score=round(clamp((unique/n*100)*.6+((1-share)*100)*.4),1)
    level="HIGH" if score>=70 else "MEDIUM" if score>=40 else "LOW"
    return {"score":score,"level":level,"evidence":f"{unique} unique channels among {n} videos; top 3 hold {share*100:.1f}% of sample views. Sample competition only."}

def calculate_performance(v):
    if len(v)<3:return 0
    a=[max(x["views"],0) for x in v]; top=max(a)
    return round(clamp((statistics.median(a)/top*100)*.6+(statistics.mean(a)/top*100)*.4),1) if top else 0

def calculate_velocity_score(v):
    if len(v)<3:return 0
    a=[max(x["views_per_day"],0) for x in v if x["views_per_day"]>0]
    if not a:return 0
    return round(clamp(statistics.median(a)/max(a)*100),1)

def save_validation(rid,val):
    db=get_db(); cur=db.cursor(); cur.execute("DELETE FROM opportunity_validation WHERE research_id=?",(rid,))
    cur.execute("""INSERT INTO opportunity_validation
    (research_id,demand_score,demand_level,demand_evidence,hype_score,hype_level,hype_evidence,
    competition_score,competition_level,competition_evidence,performance_score,velocity_score,
    opportunity_score,opportunity_level,decision,decision_reason,created_at)
    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
    (rid,val["demand_score"],val["demand_level"],val["demand_evidence"],val["hype_score"],val["hype_level"],
     val["hype_evidence"],val["competition_score"],val["competition_level"],val["competition_evidence"],
     val["performance_score"],val["velocity_score"],val["opportunity_score"],val["opportunity_level"],
     val["decision"],val["decision_reason"],datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    db.commit(); db.close()

def get_latest_validation(rid):
    db=get_db(); r=db.execute("""SELECT demand_score,demand_level,demand_evidence,hype_score,hype_level,
    hype_evidence,competition_score,competition_level,competition_evidence,performance_score,velocity_score,
    opportunity_score,opportunity_level,decision,decision_reason,created_at
    FROM opportunity_validation WHERE research_id=? ORDER BY id DESC LIMIT 1""",(rid,)).fetchone(); db.close()
    if not r:return None
    return dict(zip(["demand_score","demand_level","demand_evidence","hype_score","hype_level","hype_evidence",
                     "competition_score","competition_level","competition_evidence","performance_score",
                     "velocity_score","opportunity_score","opportunity_level","decision","decision_reason","created_at"],r))

def validate_opportunity(rid,v):
    if len(v)<3:
        val={"demand_score":0,"demand_level":"UNKNOWN","demand_evidence":"Dataset too small.",
             "hype_score":0,"hype_level":"UNKNOWN","hype_evidence":"Not enough dated videos.",
             "competition_score":0,"competition_level":"UNKNOWN","competition_evidence":"Not enough videos.",
             "performance_score":0,"velocity_score":0,"opportunity_score":0,"opportunity_level":"UNKNOWN",
             "decision":"RESEARCH MORE","decision_reason":"Dataset too small for a meaningful decision."}
        save_validation(rid,val); return val
    d,h,c=calculate_demand(v),calculate_hype(v),calculate_competition(v)
    p,vel=calculate_performance(v),calculate_velocity_score(v)
    if h["level"]=="UNKNOWN":
        score=0; level="UNKNOWN"; decision="RESEARCH MORE"
        reason="Demand and performance signals exist, but trend direction cannot be established."
    else:
        score=round(clamp(d["score"]*.30+h["score"]*.25+p*.20+vel*.15+(100-c["score"])*.10),1)
        level="HIGH" if score>=75 else "MEDIUM-HIGH" if score>=60 else "MEDIUM" if score>=40 else "LOW"
        decision="MAKE" if score>=75 else "TEST" if score>=60 else "WATCH" if score>=40 else "RESEARCH MORE"
        reason=f"Demand {d['level']}, hype {h['level']}, competition {c['level']}; performance {p}/100 and velocity {vel}/100."
    val={"demand_score":d["score"],"demand_level":d["level"],"demand_evidence":d["evidence"],
         "hype_score":h["score"],"hype_level":h["level"],"hype_evidence":h["evidence"],
         "competition_score":c["score"],"competition_level":c["level"],"competition_evidence":c["evidence"],
         "performance_score":p,"velocity_score":vel,"opportunity_score":score,"opportunity_level":level,
         "decision":decision,"decision_reason":reason}
    save_validation(rid,val); return val

def calculate_idea_score(potential,confidence,priority):
    score=50+({"HIGH":20,"MEDIUM":10}.get(potential,0))+({"HIGH":15,"MEDIUM":10,"LOW":3}.get(confidence,0))+({"HIGH":10,"MEDIUM":5}.get(priority,0))
    return min(score,100)

def generate_ideas(rid,oid,op):
    base=calculate_idea_score(op["potential"],op["confidence"],op["priority"]); e=op["evidence"]
    ideas=[]
    templates={
      "Performance":[("New video inspired by top performer","Fresh hook and original execution.","YouTube Video",0),("Winning topic as a Short","Extract the strongest curiosity point.","YouTube Short",-3),("Stronger variation of winning concept","Try a different question, twist or framing.","YouTube Video",-5)],
      "Engagement":[("Interaction-driven video","Use an open question or debate to encourage response.","YouTube Video",0),("Comment-focused Short","End with a meaningful audience choice.","YouTube Short",-4),("Two audience angles experiment","Test different hooks for the same topic.","Experiment",-6)],
      "Velocity":[("Fast-response version","React quickly while attention is strong.","YouTube Video",0),("Fast-moving topic as a Short","Deliver the most interesting information quickly.","YouTube Short",-3),("Rapid publishing experiment","Compare early performance against baseline.","Experiment",-5)],
      "Research":[("Expand research sample","Collect more evidence before a major decision.","Research",0),("Small content test","Run a low-cost test instead of a major production.","YouTube Short",-5),("Find stronger competitor evidence","Research more channels before deciding.","Research",-8)]
    }
    for title,angle,fmt,delta in templates.get(op["type"],templates["Research"]):
        ideas.append((title,angle,"Target niche audience",fmt,e,max(base+delta,0)))
    db=get_db(); cur=db.cursor(); cur.execute("DELETE FROM ideas WHERE opportunity_id=?",(oid,))
    for x in ideas:
        cur.execute("""INSERT INTO ideas(research_id,opportunity_id,title,angle,audience,format,evidence,score,status,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?)""",(rid,oid,*x,"NEW",datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    db.commit(); db.close(); return ideas

def get_ideas(rid):
    db=get_db(); rows=db.execute("""SELECT id,opportunity_id,title,angle,audience,format,evidence,score,status,created_at
    FROM ideas WHERE research_id=? ORDER BY score DESC,id DESC""",(rid,)).fetchall(); db.close()
    keys=["id","opportunity_id","title","angle","audience","format","evidence","score","status","created_at"]
    return [dict(zip(keys,r)) for r in rows]

def mark_idea_saved(iid):
    db=get_db(); db.execute("UPDATE ideas SET status='SAVED' WHERE id=?",(iid,)); db.commit(); db.close()

def get_dashboard_data():
    db=get_db()
    counts={}
    for table,key in [("research","research_count"),("videos","video_count"),("opportunities","opportunity_count"),("ideas","idea_count")]:
        counts[key]=db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    counts["saved_ideas"]=db.execute("SELECT COUNT(*) FROM ideas WHERE status='SAVED'").fetchone()[0]
    r=db.execute("SELECT id,name,keyword,created_at FROM research ORDER BY id DESC LIMIT 1").fetchone()
    v=get_latest_validation(r[0]) if r else None
    op=db.execute("""SELECT title,potential,priority,suggested_action FROM opportunities
                    ORDER BY id DESC LIMIT 1""").fetchone()
    db.close()
    return {**counts,"latest":r,"validation":v,"top_opportunity":op}

class HomeScreen(Screen):
    def __init__(self,**kwargs):
        super().__init__(**kwargs); root=BoxLayout(orientation="vertical",padding=dp(20),spacing=dp(14))
        add_label(root,"DEXRO",34,55); add_label(root,"Research & Decision Intelligence",17,45)
        add_label(root,"Turn data into better content decisions.",15,55)
        for text,target in [("＋  NEW RESEARCH","research"),("▣  RESEARCH HISTORY","history"),("◉  DASHBOARD","dashboard")]:
            b=Button(text=text,size_hint_y=None,height=dp(60)); b.bind(on_press=lambda x,t=target:setattr(self.manager,"current",t)); root.add_widget(b)
        add_label(root,"\nRESEARCH → ANALYSIS → VALIDATION → OPPORTUNITY → IDEA",13,65); self.add_widget(root)

class DashboardScreen(Screen):
    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        root=BoxLayout(orientation="vertical",padding=dp(15),spacing=dp(10))
        add_label(root,"DEXRO DASHBOARD",28,55); add_label(root,"COMMAND CENTER",15,40)
        self.scroll=ScrollView(); self.content=BoxLayout(orientation="vertical",spacing=dp(10),padding=dp(5),size_hint_y=None)
        self.content.bind(minimum_height=self.content.setter("height")); self.scroll.add_widget(self.content); root.add_widget(self.scroll)
        for text,target in [("＋ NEW RESEARCH","research"),("▣ RESEARCH HISTORY","history"),("← BACK HOME","home")]:
            b=Button(text=text,size_hint_y=None,height=dp(52)); b.bind(on_press=lambda x,t=target:setattr(self.manager,"current",t)); root.add_widget(b)
        self.add_widget(root)
    def on_enter(self): self.load()
    def load(self):
        self.content.clear_widgets(); d=get_dashboard_data()
        add_label(self.content,"SYSTEM OVERVIEW",19,45)
        add_label(self.content,f"Research: {d['research_count']}   Videos: {d['video_count']}\nOpportunities: {d['opportunity_count']}   Ideas: {d['idea_count']}   Saved Ideas: {d['saved_ideas']}",16,85)
        if not d["latest"]:
            add_label(self.content,"No research yet.\nStart a new research project.",17,80); return
        r=d["latest"]; add_label(self.content,f"LATEST RESEARCH\n{r[1]}\nKeyword: {r[2]}\nCreated: {r[3]}",16,110)
        v=d["validation"]
        if v:
            add_label(self.content,"FINAL DECISION",19,45)
            add_label(self.content,f"{v['decision']}\nOpportunity Score: {v['opportunity_score']}/100\nLevel: {v['opportunity_level']}",22,100)
            add_label(self.content,f"Demand: {v['demand_level']} ({v['demand_score']}/100)\nHype: {v['hype_level']} ({v['hype_score']}/100)\nCompetition: {v['competition_level']} ({v['competition_score']}/100)\nPerformance: {v['performance_score']}/100\nVelocity: {v['velocity_score']}/100",16,180)
            add_label(self.content,"Decision Reason\n"+v["decision_reason"],15,100)
        else: add_label(self.content,"No validation yet.\nOpen research history and run validation.",16,80)
        if d["top_opportunity"]:
            o=d["top_opportunity"]; add_label(self.content,f"TOP OPPORTUNITY\n{o[0]}\nPotential: {o[1]}  Priority: {o[2]}\nAction: {o[3]}",16,105)

class ResearchScreen(Screen):
    def __init__(self,**kwargs):
        super().__init__(**kwargs); self.last_results=[]
        root=BoxLayout(orientation="vertical",padding=dp(18),spacing=dp(12)); add_label(root,"NEW RESEARCH",27,55)
        self.name_input=TextInput(hint_text="Research name",multiline=False,size_hint_y=None,height=dp(50))
        self.question_input=TextInput(hint_text="Research question",multiline=False,size_hint_y=None,height=dp(50))
        self.keyword_input=TextInput(hint_text="YouTube keyword",multiline=False,size_hint_y=None,height=dp(50))
        for x in [self.name_input,self.question_input,self.keyword_input]: root.add_widget(x)
        for text,fn,h in [("SEARCH & ANALYZE",self.search,60),("SAVE RESEARCH",self.save,60),("BACK",lambda x:setattr(self.manager,"current","home"),50)]:
            b=Button(text=text,size_hint_y=None,height=dp(h)); b.bind(on_press=fn); root.add_widget(b)
        self.status=Label(text="",size_hint_y=None,height=dp(70)); root.add_widget(self.status); self.add_widget(root)
    def search(self,instance):
        try:
            results=youtube_search(self.keyword_input.text.strip()); ids=[x["youtube_id"] for x in results]
            self.last_results=calculate_metrics(results,get_statistics(ids))
            self.manager.get_screen("results").set_results(self.last_results); self.manager.current="results"
        except Exception as e:self.status.text=str(e)
    def save(self,instance):
        if not self.last_results:self.status.text="Search first, then save."; return
        kw=self.keyword_input.text.strip(); name=self.name_input.text.strip() or kw
        rid=save_research(name,self.question_input.text.strip(),kw,self.last_results); generate_opportunities(rid,self.last_results)
        self.status.text="✓ Research saved."

class ResultsScreen(Screen):
    def __init__(self,**kwargs):
        super().__init__(**kwargs); root=BoxLayout(orientation="vertical",padding=dp(15),spacing=dp(10)); add_label(root,"YOUTUBE RESULTS",25,50)
        self.scroll=ScrollView(); self.content=BoxLayout(orientation="vertical",spacing=dp(10),size_hint_y=None); self.content.bind(minimum_height=self.content.setter("height")); self.scroll.add_widget(self.content); root.add_widget(self.scroll)
        b=Button(text="BACK TO RESEARCH",size_hint_y=None,height=dp(55)); b.bind(on_press=lambda x:setattr(self.manager,"current","research")); root.add_widget(b); self.add_widget(root)
    def set_results(self,videos):
        self.content.clear_widgets()
        for i,v in enumerate(videos,1): add_label(self.content,f"{i}. {short_title(v['title'])}\n{v['channel']}\nViews {format_number(v['views'])}  Likes {format_number(v['likes'])}\nEngagement {v['engagement']:.2f}%  Views/day {format_number(v['views_per_day'])}",15,125)

class HistoryScreen(Screen):
    def __init__(self,**kwargs):
        super().__init__(**kwargs); root=BoxLayout(orientation="vertical",padding=dp(15),spacing=dp(10)); add_label(root,"RESEARCH HISTORY",26,55)
        self.scroll=ScrollView(); self.content=BoxLayout(orientation="vertical",spacing=dp(10),size_hint_y=None); self.content.bind(minimum_height=self.content.setter("height")); self.scroll.add_widget(self.content); root.add_widget(self.scroll)
        b=Button(text="BACK HOME",size_hint_y=None,height=dp(55)); b.bind(on_press=lambda x:setattr(self.manager,"current","home")); root.add_widget(b); self.add_widget(root)
    def on_enter(self): self.load()
    def load(self):
        self.content.clear_widgets(); rows=get_history()
        if not rows:add_label(self.content,"No saved research yet.",17,60); return
        for r in rows:
            b=Button(text=f"{r[1]}\n{r[3]}  •  {r[4]}",size_hint_y=None,height=dp(85))
            b.bind(on_press=lambda x,rid=r[0]:self.open_analysis(rid)); self.content.add_widget(b)
    def open_analysis(self,rid):
        self.manager.get_screen("analysis").set_research(rid); self.manager.current="analysis"

class AnalysisScreen(Screen):
    def __init__(self,**kwargs):
        super().__init__(**kwargs); self.research_id=None
        root=BoxLayout(orientation="vertical",padding=dp(15),spacing=dp(10)); add_label(root,"RESEARCH ANALYSIS",26,55)
        self.scroll=ScrollView(); self.content=BoxLayout(orientation="vertical",spacing=dp(10),padding=dp(5),size_hint_y=None); self.content.bind(minimum_height=self.content.setter("height")); self.scroll.add_widget(self.content); root.add_widget(self.scroll)
        for text,fn,h in [("🎯 VALIDATE OPPORTUNITY",self.open_validation,60),("🔎 VIEW OPPORTUNITIES",self.open_opportunities,60),("VIEW VIDEOS",self.open_videos,52),("BACK TO HISTORY",lambda x:setattr(self.manager,"current","history"),48)]:
            b=Button(text=text,size_hint_y=None,height=dp(h)); b.bind(on_press=fn); root.add_widget(b)
        self.add_widget(root)
    def set_research(self,rid):
        self.research_id=rid; v=get_research_videos(rid); self.content.clear_widgets()
        if not v:add_label(self.content,"No video data found.",17,60); return
        views=[x["views"] for x in v]; likes=[x["likes"] for x in v]; comments=[x["comments"] for x in v]; eng=[x["engagement"] for x in v]; vel=[x["views_per_day"] for x in v]
        add_label(self.content,f"{len(v)} videos analyzed",16,55)
        add_label(self.content,f"Average Views {format_number(statistics.mean(views))}\nMedian Views {format_number(statistics.median(views))}\nAverage Likes {format_number(statistics.mean(likes))}\nAverage Comments {format_number(statistics.mean(comments))}\nAvg Engagement {statistics.mean(eng):.2f}%\nAverage Views/day {format_number(statistics.mean(vel))}",16,190)
        top=sorted(v,key=lambda x:x["views"],reverse=True)[:3]; add_label(self.content,"TOP 3 BY VIEWS\n"+"\n".join(f"{i}. {short_title(x['title'],55)} — {format_number(x['views'])}" for i,x in enumerate(top,1)),16,140)
        be=max(v,key=lambda x:x["engagement"]); bv=max(v,key=lambda x:x["views_per_day"])
        add_label(self.content,f"STRONGEST SIGNALS\nEngagement: {be['engagement']:.2f}%\nVelocity: {format_number(bv['views_per_day'])} views/day",16,100)
    def open_validation(self,x): self.manager.get_screen("validation").set_research(self.research_id); self.manager.current="validation"
    def open_opportunities(self,x): self.manager.get_screen("opportunities").set_research(self.research_id); self.manager.current="opportunities"
    def open_videos(self,x): self.manager.get_screen("saved_results").set_results(get_research_videos(self.research_id)); self.manager.current="saved_results"

class OpportunityValidationScreen(Screen):
    def __init__(self,**kwargs):
        super().__init__(**kwargs); self.research_id=None; root=BoxLayout(orientation="vertical",padding=dp(15),spacing=dp(10)); add_label(root,"OPPORTUNITY VALIDATION",26,55)
        b=Button(text="🔥 RUN VALIDATION",size_hint_y=None,height=dp(58)); b.bind(on_press=self.run_validation); root.add_widget(b)
        self.scroll=ScrollView(); self.content=BoxLayout(orientation="vertical",spacing=dp(12),padding=dp(5),size_hint_y=None); self.content.bind(minimum_height=self.content.setter("height")); self.scroll.add_widget(self.content); root.add_widget(self.scroll)
        b=Button(text="← BACK TO ANALYSIS",size_hint_y=None,height=dp(55)); b.bind(on_press=lambda x:setattr(self.manager,"current","analysis")); root.add_widget(b); self.add_widget(root)
    def set_research(self,rid): self.research_id=rid; self.run_validation(None)
    def run_validation(self,x):
        self.content.clear_widgets()
        if self.research_id is None:return
        v=validate_opportunity(self.research_id,get_research_videos(self.research_id))
        add_label(self.content,f"FINAL DECISION\n{v['decision']}\nOpportunity Score: {v['opportunity_score']}/100\nLevel: {v['opportunity_level']}",21,110)
        add_label(self.content,"Reason\n"+v["decision_reason"],15,90)
        for title,score,level,evidence in [("AUDIENCE DEMAND",v["demand_score"],v["demand_level"],v["demand_evidence"]),("HYPE / TREND",v["hype_score"],v["hype_level"],v["hype_evidence"]),("COMPETITION",v["competition_score"],v["competition_level"],v["competition_evidence"])]:
            add_label(self.content,f"{title}\nScore: {score}/100  Level: {level}\n{evidence}",15,145)
        add_label(self.content,f"PERFORMANCE & VELOCITY\nPerformance: {v['performance_score']}/100\nVelocity: {v['velocity_score']}/100",16,85)

class OpportunitiesScreen(Screen):
    def __init__(self,**kwargs):
        super().__init__(**kwargs); self.research_id=None; root=BoxLayout(orientation="vertical",padding=dp(15),spacing=dp(10)); add_label(root,"OPPORTUNITIES",27,55)
        b=Button(text="💡 CREATE IDEAS",size_hint_y=None,height=dp(60)); b.bind(on_press=self.open_ideas); root.add_widget(b)
        self.scroll=ScrollView(); self.content=BoxLayout(orientation="vertical",spacing=dp(14),padding=dp(5),size_hint_y=None); self.content.bind(minimum_height=self.content.setter("height")); self.scroll.add_widget(self.content); root.add_widget(self.scroll)
        b=Button(text="← BACK TO ANALYSIS",size_hint_y=None,height=dp(55)); b.bind(on_press=lambda x:setattr(self.manager,"current","analysis")); root.add_widget(b); self.add_widget(root)
    def set_research(self,rid):
        self.research_id=rid; generate_opportunities(rid,get_research_videos(rid)); self.content.clear_widgets()
        for op in get_opportunities(rid):
            add_label(self.content,f"{op['title']}\n{op['description']}\nEvidence: {op['evidence']}\nPotential: {op['potential']}  Confidence: {op['confidence']}\nPriority: {op['priority']}  Action: {op['action']}",15,270)
    def open_ideas(self,x): self.manager.get_screen("ideas").set_research(self.research_id); self.manager.current="ideas"

class IdeasScreen(Screen):
    def __init__(self,**kwargs):
        super().__init__(**kwargs); self.research_id=None; root=BoxLayout(orientation="vertical",padding=dp(15),spacing=dp(10)); add_label(root,"💡 IDEA ENGINE",27,55)
        self.scroll=ScrollView(); self.content=BoxLayout(orientation="vertical",spacing=dp(14),padding=dp(5),size_hint_y=None); self.content.bind(minimum_height=self.content.setter("height")); self.scroll.add_widget(self.content); root.add_widget(self.scroll)
        b=Button(text="← BACK TO OPPORTUNITIES",size_hint_y=None,height=dp(55)); b.bind(on_press=lambda x:setattr(self.manager,"current","opportunities")); root.add_widget(b); self.add_widget(root)
    def set_research(self,rid):
        self.research_id=rid; self.content.clear_widgets()
        for op in get_opportunities(rid): generate_ideas(rid,op["id"],op)
        for idea in get_ideas(rid):
            add_label(self.content,f"{idea['title']}\nANGLE: {idea['angle']}\nAUDIENCE: {idea['audience']}\nFORMAT: {idea['format']}\nEVIDENCE: {idea['evidence']}\nSCORE: {idea['score']}/100  STATUS: {idea['status']}",15,260)
            b=Button(text="✓ SAVE IDEA",size_hint_y=None,height=dp(48)); b.bind(on_press=lambda x,i=idea["id"]:self.save_idea(i)); self.content.add_widget(b)
    def save_idea(self,iid): mark_idea_saved(iid); self.set_research(self.research_id)

class SavedResultsScreen(Screen):
    def __init__(self,**kwargs):
        super().__init__(**kwargs); root=BoxLayout(orientation="vertical",padding=dp(15),spacing=dp(10)); add_label(root,"SAVED VIDEOS",25,50)
        self.scroll=ScrollView(); self.content=BoxLayout(orientation="vertical",spacing=dp(10),size_hint_y=None); self.content.bind(minimum_height=self.content.setter("height")); self.scroll.add_widget(self.content); root.add_widget(self.scroll)
        b=Button(text="← BACK TO ANALYSIS",size_hint_y=None,height=dp(55)); b.bind(on_press=lambda x:setattr(self.manager,"current","analysis")); root.add_widget(b); self.add_widget(root)
    def set_results(self,videos):
        self.content.clear_widgets()
        for i,v in enumerate(videos,1): add_label(self.content,f"{i}. {short_title(v['title'])}\n{v['channel']}\nViews: {format_number(v['views'])}\nLikes: {format_number(v['likes'])}\nComments: {format_number(v['comments'])}\nEngagement: {v['engagement']:.2f}%\nViews/day: {format_number(v['views_per_day'])}",15,150)

class DexroApp(App):
    def build(self):
        setup_database(); manager=ScreenManager()
        for cls,name in [(HomeScreen,"home"),(DashboardScreen,"dashboard"),(ResearchScreen,"research"),
                         (ResultsScreen,"results"),(HistoryScreen,"history"),(AnalysisScreen,"analysis"),
                         (OpportunityValidationScreen,"validation"),(OpportunitiesScreen,"opportunities"),
                         (IdeasScreen,"ideas"),(SavedResultsScreen,"saved_results")]:
            manager.add_widget(cls(name=name))
        return manager

if __name__ == "__main__":
    DexroApp().run()
