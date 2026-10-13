#!/usr/bin/env python3
"""CH-666 daily story pipeline. Real news only; no mock fallback."""
import argparse, base64, hashlib, json, os, random, re, sys, time
from datetime import datetime, timedelta, timezone
from ftplib import FTP
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse
import requests

UTC=timezone.utc
CHANNELS={
"3":{"channel":"CH-333","name":"靈頻頻道","types":["possession","haunting","ritual","curse","mediumship","ancestral_sin","spirit_contract","exorcism","afterlife_glimpse","folk_belief"],"fantasy":["slightly_unreal","supernatural","reality_bending","mythic"],"styles":["first_person","third_person_limited","epistolary","found_footage","interview_transcript","diary_entry","ritual_record","oral_tradition"]},
"6":{"channel":"CH-666","name":"怪聞頻道","types":["psychological","urban_legend","supernatural","crime","suspense","identity_horror","sci_fi_horror","surveillance_horror","unknown_phenomenon","reality_horror"],"fantasy":["grounded","slightly_unreal","supernatural","reality_bending"],"styles":["first_person","third_person_limited","third_person_omniscient","epistolary","found_footage","interview_transcript","police_report","diary_entry"]},
"9":{"channel":"CH-999","name":"禁忌頻道","types":["cognitive_hazard","memetic","ontological","reality_horror","cosmic_horror","body_horror_extreme","time_loop","identity_horror","forbidden_knowledge","apocalyptic"],"fantasy":["supernatural","reality_bending","mythic","conceptual"],"styles":["first_person","third_person_omniscient","epistolary","found_footage","interview_transcript","police_report","research_log","fragmented_memory"]}}
ENDINGS=["open","twist","tragic","unsettling_resolution","cyclic","missing_ending"]
PACINGS=["slow_burn","steady","fast_paced","fragmented","disorienting"]
PERSPECTIVES=["victim","witness","investigator","bystander","entity","object"]

def log(s): print(s,flush=True)
def load_story_skill_guidance():
    """Load the repository's reusable story-writing skill modules."""
    path=Path(__file__).resolve().parent.parent/"config"/"story_skills.md"
    try:
        return path.read_text(encoding="utf-8")
    except OSError as e:
        log(f"WARNING: story skills file unavailable; using inline baseline: {e}")
        return "先規劃角色目標、線索、轉折與結局；檢查時間線和人物動機；以繁體中文修訂並遵守 HTML 閱讀排版規則。"
def now_iso(): return datetime.now(UTC).isoformat().replace("+00:00","Z")
def output(vals):
    p=os.getenv("GITHUB_OUTPUT")
    if p:
        with open(p,"a",encoding="utf-8") as f:
            for k,v in vals.items(): f.write(f"{k}={str(v).replace(chr(10),' ')}\n")

def _article_row(title,url,pub,target,domain=""):
    title=re.sub(r"\s+"," ",(title or "").strip())
    url=(url or "").strip()
    if not title or not url or urlparse(url).scheme not in ("http","https"): return None
    date=target
    if pub:
        try:
            from email.utils import parsedate_to_datetime
            dt=parsedate_to_datetime(pub)
            if dt: date=dt.astimezone(UTC).strftime("%Y-%m-%d")
        except Exception: pass
        compact=re.sub(r"[^0-9]","",pub)
        if len(compact)>=8 and compact[:8].startswith(("19","20")):
            date=f"{compact[:4]}-{compact[4:6]}-{compact[6:8]}"
    return {"source_title":title,"source_summary":(domain or "")+" | "+(pub or ""),"source_content":"","source_url":url,"source_date":date,"source_location":"台灣/亞洲新聞","source_language":"zh","source_kind":"recent_news","case_date":"","unusual_detail":title,"event":title,"people":[],"source_hash":hashlib.sha256((title+"|"+url).encode()).hexdigest()[:12],"event_hash":hashlib.sha256(re.sub(r"\W","",title.lower()).encode()).hexdigest()[:12]}

def _fetch_gdelt(params):
    url="https://api.gdeltproject.org/api/v2/doc/doc"
    last=None
    for attempt in range(5):
        try:
            r=requests.get(url,params=params,timeout=40,headers={"User-Agent":"Mozilla/5.0 CH666-story-pipeline/3.1"})
            if r.status_code==429:
                wait=r.headers.get("Retry-After","")
                try: delay=min(45,max(2,int(wait)))
                except (ValueError,TypeError): delay=min(30,3*(2**attempt))
                last=RuntimeError("GDELT rate limited (HTTP 429)")
                if attempt<4:
                    log(f"WARNING: GDELT rate limited; retry {attempt+1}/4 after {delay}s")
                    time.sleep(delay)
                    continue
                break
            if r.status_code in (500,502,503,504) and attempt<4:
                delay=min(20,2**(attempt+1)); log(f"WARNING: GDELT HTTP {r.status_code}; retry after {delay}s"); time.sleep(delay); continue
            r.raise_for_status()
            return r.json().get("articles",[]) or []
        except requests.RequestException as e:
            last=e
            if attempt<4:
                delay=min(20,2**(attempt+1)); log(f"WARNING: GDELT request failed ({e}); retry after {delay}s"); time.sleep(delay)
            else: break
    log(f"WARNING: GDELT unavailable after retries: {last}")
    return None

def _fetch_google_news_rss(target,count):
    """Real-news fallback only; never invent or fabricate article records."""
    import xml.etree.ElementTree as ET
    from urllib.parse import quote_plus
    query=quote_plus('(台灣 OR 台北 OR 高雄 OR 日本 OR 韓國) (異常 OR 神秘 OR 失蹤 OR 詭異 OR 事故)')
    url="https://news.google.com/rss/search?q="+query+"&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    last=None
    for attempt in range(3):
        try:
            r=requests.get(url,timeout=35,headers={"User-Agent":"Mozilla/5.0 (compatible; CH666NewsBot/1.0)"})
            if r.status_code==429 and attempt<2:
                delay=3*(attempt+1); log(f"WARNING: Google News RSS rate limited; retry after {delay}s"); time.sleep(delay); continue
            r.raise_for_status()
            root=ET.fromstring(r.content)
            rows=[]; seen=set()
            for item in root.findall(".//item"):
                title=item.findtext("title","").strip()
                link=item.findtext("link","").strip()
                pub=item.findtext("pubDate","").strip()
                source=item.find("source")
                domain=(source.text or "").strip() if source is not None else "Google News RSS"
                row=_article_row(title,link,pub,target,domain)
                if not row or row["source_url"] in seen: continue
                # Keep only articles whose publication date matches the requested date where the date parses.
                if row["source_date"] != target: continue
                seen.add(row["source_url"]); rows.append(row)
                if len(rows)>=count: break
            return rows
        except Exception as e:
            last=e
            if attempt<2: time.sleep(2*(attempt+1))
    log(f"WARNING: Google News RSS fallback failed: {last}")
    return []

def _rss_pub_date(value):
    """Return a strict UTC date for RSS/Atom timestamps; unknown dates are rejected."""
    from email.utils import parsedate_to_datetime
    value=(value or "").strip()
    if not value: return None
    try:
        dt=parsedate_to_datetime(value)
        if dt:
            if dt.tzinfo is None: dt=dt.replace(tzinfo=UTC)
            return dt.astimezone(UTC).strftime("%Y-%m-%d")
    except Exception: pass
    try:
        dt=datetime.fromisoformat(value.replace("Z","+00:00"))
        if dt.tzinfo is None: dt=dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC).strftime("%Y-%m-%d")
    except Exception: return None

def _parse_rss_feed(feed_url,source_name,target,limit=30):
    """Parse RSS 2.0 or Atom using stdlib XML; keep only dated real articles."""
    import xml.etree.ElementTree as ET
    rows=[]
    try:
        response=requests.get(feed_url,timeout=12,headers={"User-Agent":"Mozilla/5.0 (compatible; CH666NewsBot/1.0)"})
        response.raise_for_status()
        root=ET.fromstring(response.content)
        def local(tag): return tag.rsplit("}",1)[-1].lower()
        for node in root.iter():
            if local(node.tag) not in ("item","entry"): continue
            fields={}
            for child in list(node):
                key=local(child.tag)
                if key=="link":
                    fields["link"]=child.attrib.get("href","").strip() or (child.text or "").strip()
                elif key in ("title","pubdate","published","updated","date","description","summary"):
                    fields[key]=(child.text or "").strip()
            title=fields.get("title","")
            link=fields.get("link","")
            pub=fields.get("pubdate") or fields.get("published") or fields.get("updated") or fields.get("date","")
            if _rss_pub_date(pub)!=target: continue
            row=_article_row(title,link,pub,target,source_name)
            if row:
                row["source_summary"]=(source_name+" | "+(fields.get("summary") or fields.get("description") or title))[:1200]
                rows.append(row)
                if len(rows)>=limit: break
    except Exception as e:
        log(f"  RSS source unavailable ({source_name}): {e}")
    return rows

def _fetch_newsdir_rss(target,count):
    """Use the public NEWS-dir source registry as an RSS fallback, not its stale daily JSON."""
    config_url="https://raw.githubusercontent.com/lovemidog001/NEWS-dir/main/config/sources.json"
    try:
        response=requests.get(config_url,timeout=12,headers={"User-Agent":"CH666-story-pipeline/1.0"})
        response.raise_for_status()
        config=response.json()
        sources=config.get("sources",[]) if isinstance(config,dict) else []
    except Exception as e:
        log(f"WARNING: NEWS-dir source registry unavailable: {e}")
        return []
    # Prioritize social/lifestyle/entertainment and broad Taiwan news over specialist feeds.
    priority={"cna_social":0,"cna_lifehealth":1,"cna_entertainment":2,"ltn":3,"udn_news":4,"tvbs_news":5,"storm_media":6,"cna_politics":7,"cna_finance":8,"cna_technology":9,"ithome":10,"inside":11,"cna_sport":12}
    sources=sorted((s for s in sources if s.get("enabled") and s.get("type")=="rss" and s.get("url")),key=lambda s:priority.get(s.get("id"),99))
    rows=[]; seen=set()
    for source in sources:
        for row in _parse_rss_feed(source["url"],source.get("name") or source.get("id") or "NEWS-dir RSS",target,count-len(rows)):
            if row["source_url"] not in seen:
                seen.add(row["source_url"]); rows.append(row)
            if len(rows)>=count: break
        if len(rows)>=count: break
    log(f"INFO: NEWS-dir RSS provided {len(rows)} usable real articles.")
    return rows[:count]

def _fetch_newsbot_rss(target,count):
    """Use the public news-bot feed list as the final, tech/gaming-heavy fallback."""
    config_url="https://raw.githubusercontent.com/lovemidog001/news-bot/main/rss_sources.json"
    try:
        response=requests.get(config_url,timeout=12,headers={"User-Agent":"CH666-story-pipeline/1.0"})
        response.raise_for_status()
        sources=response.json()
        if not isinstance(sources,list): raise ValueError("RSS source list is not an array")
    except Exception as e:
        log(f"WARNING: news-bot RSS registry unavailable: {e}")
        return []
    rows=[]; seen=set()
    for source in sources:
        if not isinstance(source,dict) or not source.get("url"): continue
        name=source.get("name") or source.get("category") or "news-bot RSS"
        for row in _parse_rss_feed(source["url"],name,target,count-len(rows)):
            if row["source_url"] not in seen:
                seen.add(row["source_url"]); rows.append(row)
            if len(rows)>=count: break
        if len(rows)>=count: break
    log(f"INFO: news-bot RSS provided {len(rows)} usable real articles.")
    return rows[:count]

def fetch_historical_cases(target,count,exclude_urls=None):
    """Collect older real cases from Wikipedia search; never fabricate a case record."""
    if count <= 0: return []
    endpoint="https://en.wikipedia.org/w/api.php"
    queries=[
        '"Wisconsin suitcase" murder case',
        '"Baton Rouge" serial killer case',
        '"Joanna Lopez" missing case',
        'historical unsolved murder cold case',
        'famous disappearance investigation case',
        'serial murder investigation case',
        'mysterious historical disappearance'
    ]
    rows=[]; seen=set(); exclude_urls=set(exclude_urls or [])
    headers={"User-Agent":"ODDITY-HUB-ResearchBot/1.0 (fiction research; contact via GitHub repository)"}
    for query in queries:
        if len(rows)>=count: break
        try:
            response=requests.get(endpoint,params={
                "action":"query","format":"json","generator":"search",
                "gsrsearch":query,"gsrnamespace":0,"gsrlimit":20,"gsroffset":0,
                "prop":"extracts|info","exintro":1,"explaintext":1,"inprop":"url"
            },headers=headers,timeout=18)
            response.raise_for_status()
            pages=response.json().get("query",{}).get("pages",{})
            ordered=sorted(pages.values(),key=lambda page:page.get("index",9999))
            for page in ordered:
                title=re.sub(r"\\s+"," ",(page.get("title") or "").strip())
                extract=re.sub(r"\\s+"," ",(page.get("extract") or "").strip())
                url=(page.get("fullurl") or "").strip()
                if not title or not extract or not url or len(extract)<180 or url in exclude_urls: continue
                key=hashlib.sha256(re.sub(r"\\W","",title.lower()).encode()).hexdigest()[:12]
                if key in seen: continue
                seen.add(key)
                rows.append({
                    "source_title":title,
                    "source_summary":("Historical case reference | Wikipedia article extract: "+extract)[:1800],
                    "source_content":extract[:5000],
                    "source_url":url,
                    "source_date":target,
                    "case_date":"",
                    "source_location":"Historical case; see cited source article",
                    "source_language":"en",
                    "source_kind":"historical_case",
                    "unusual_detail":extract[:500],
                    "event":title,
                    "people":[],
                    "source_hash":hashlib.sha256((title+"|"+url).encode()).hexdigest()[:12],
                    "event_hash":key
                })
                if len(rows)>=count: break
        except Exception as e:
            log(f"  Historical case search unavailable ({query}): {e}")
        time.sleep(0.25)
    log(f"INFO: historical case search provided {len(rows)} sourced case records.")
    return rows[:count]

def fetch_story_sources(target,count,case_dir=None):
    """Mix recent real news with sourced historical cases; fall back only to real records."""
    recent_target=(count+1)//2
    recent=fetch_news(target,recent_target)
    seen={row.get("event_hash") for row in recent}
    known_urls=set()
    if case_dir and Path(case_dir).exists():
        for case_file in Path(case_dir).glob("*.json"):
            try:
                saved=json.loads(case_file.read_text(encoding="utf-8"))
                if saved.get("source_url"): known_urls.add(saved["source_url"])
            except Exception: pass
    historical=fetch_historical_cases(target,count-len(recent),exclude_urls=known_urls)
    mixed=recent[:]
    for row in historical:
        if row.get("event_hash") in seen: continue
        seen.add(row.get("event_hash")); mixed.append(row)
        if len(mixed)>=count: break
    if len(mixed)<count:
        # Try the recent-news pipeline for additional real articles if the history API is sparse.
        extra=fetch_news(target,count)
        for row in extra:
            if row.get("event_hash") in seen: continue
            seen.add(row.get("event_hash")); mixed.append(row)
            if len(mixed)>=count: break
    random.SystemRandom().shuffle(mixed)
    log(f"INFO: source mix = {sum(1 for row in mixed if row.get('source_kind')=='historical_case')} historical cases, {sum(1 for row in mixed if row.get('source_kind')!='historical_case')} recent news.")
    return mixed[:count]

def fetch_news(target,count):
    start=datetime.strptime(target,"%Y-%m-%d").replace(tzinfo=UTC)
    end=start+timedelta(days=1)
    query='(Taiwan OR 台灣 OR 高雄 OR 台北 OR 日本 OR 韓國) (mystery OR unusual OR missing OR strange OR 異常 OR 神秘 OR 失蹤 OR 詭異 OR 事故 OR 發現) sourcelang:Chinese'
    params={"query":query,"mode":"ArtList","format":"json","maxrecords":min(100,max(20,count*8)),"sort":"DateDesc","startdatetime":start.strftime("%Y%m%d%H%M%S"),"enddatetime":(end-timedelta(seconds=1)).strftime("%Y%m%d%H%M%S")}
    articles=_fetch_gdelt(params)
    rows=[]; seen=set(); seen_titles=set()
    if articles is not None:
        for a in articles:
            row=_article_row(a.get("title",""),a.get("url",""),a.get("seendate",""),target,a.get("domain",""))
            if not row or row["source_url"] in seen or row["event_hash"] in seen_titles: continue
            if row["source_date"]!=target: continue
            seen.add(row["source_url"]); seen_titles.add(row["event_hash"]); rows.append(row)
            if len(rows)>=count: break
    fallbacks=[
        ("Google News RSS",lambda n:_fetch_google_news_rss(target,n)),
        ("NEWS-dir RSS",lambda n:_fetch_newsdir_rss(target,n)),
        ("news-bot RSS",lambda n:_fetch_newsbot_rss(target,n)),
    ]
    for label,fetcher in fallbacks:
        if len(rows)>=count: break
        log(f"INFO: {label} fallback: {len(rows)} usable articles so far; requesting {count-len(rows)} more.")
        for row in fetcher(count-len(rows)):
            title_key=row.get("event_hash","")
            if row["source_url"] in seen or (title_key and title_key in seen_titles): continue
            seen.add(row["source_url"])
            if title_key: seen_titles.add(title_key)
            rows.append(row)
            if len(rows)>=count: break
    if len(rows)<count: log(f"WARNING: only {len(rows)} real articles found for {target}; no mock stories will be added.")
    return rows
def clean_image_urls(value):
    """Remove accidental whitespace from image URLs throughout nested JSON payloads."""
    if isinstance(value,dict):
        return {k: (re.sub(r"\s+","",v) if k in ("cover_image","scene_images") and isinstance(v,str) else clean_image_urls(v)) for k,v in value.items()}
    if isinstance(value,list): return [clean_image_urls(v) for v in value]
    return value

def parse_json(s):
    s=(s or "").strip(); s=re.sub(r"^\x60\x60\x60(?:json)?\s*","",s); s=re.sub(r"\s*\x60\x60\x60$","",s)
    try: return json.loads(s)
    except ValueError:
        m=re.search(r"\{.*\}",s,re.S)
        if m:
            try: return json.loads(m.group(0))
            except ValueError: pass
    return None

def call_provider(name,prompt,system):
    if name=="nvidia":
        key=os.getenv("NVIDIA_API_KEY",""); url="https://integrate.api.nvidia.com/v1/chat/completions"; model=os.getenv("NVIDIA_MODEL","nvidia/nemotron-3-super-49b-v1")
    else:
        key=os.getenv("AGNES_API_KEY",""); url="https://apihub.agnes-ai.com/v1/chat/completions"; model=os.getenv("AGNES_MODEL","agnes-2.5-flash")
    if not key: raise RuntimeError(name+" API key missing")
    body={"model":model,"messages":[{"role":"system","content":system},{"role":"user","content":prompt}],"temperature":0.85,"max_tokens":6500,"stream":False}
    last=None
    for attempt in range(2):
        try:
            r=requests.post(url,headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"},json=body,timeout=180)
            if r.status_code in (429,500,502,503,504) and attempt==0: time.sleep(3); continue
            r.raise_for_status(); obj=r.json()
            story=parse_json(obj["choices"][0]["message"]["content"])
            if not story: raise RuntimeError("invalid JSON response")
            return story,model
        except Exception as e:
            last=e
            if attempt==0: time.sleep(2)
    raise RuntimeError(f"{name} failed: {last}")

def make_story(article,cat,dice):
    c=CHANNELS[cat]
    system="你是繁體中文原創怪談作家與小說排版編輯。新聞只能當抽象靈感，不得把真實新聞改寫成故事，不可使用真實人物或機構。只輸出合法 JSON。故事 content 必須是適合手機閱讀、可供網站安全清理後直接渲染的 HTML 片段，不是 Markdown；只使用 p、strong、b、em、i、blockquote、br、span、mark、small、cite、q、ruby、rt、rp 這些標籤，允許的屬性只有 class。不得輸出 h1-h6、div、style、script、iframe、hr、img、任何 on* 事件屬性、CSS、JavaScript 或完整 HTML 文件。故事標題由獨立的 title 欄位顯示。標籤必須正確閉合。"
    prompt=f"""頻道：{c['channel']}（{c['name']}）
骰選：恐怖分數 {dice['horror_score']}/100；恐怖類型 {dice['horror_type']}；幻想等級 {dice['fantasy_level']}；敘事風格 {dice['narrative_style']}；節奏 {dice['pacing']}；結局 {dice['ending_type']}；視角 {dice['perspective']}；故事結構 {dice.get('structure','slow_reveal')}；改編切入點 {dice.get('adaptation_mode','inspired_by_core_mystery')}；揭露密度 {dice.get('reveal_density','balanced')}。
素材類型：{"歷史案件參考" if article.get("source_kind")=="historical_case" else "近期新聞靈感"}
來源標題：{article['source_title']}
來源摘要／可核對線索：{article.get('source_summary','')}
來源連結：{article.get('source_url','')}
改編原則：若是歷史案件，先分清來源中可核對的事實、調查方式、線索與仍有爭議／未知的部分；不可把推測寫成事實。若是近期新聞，只提取抽象概念。兩者都必須重新設計人物、虛構地點、動機、因果規則、情節與結局，不得照搬真實案件，也不可使用真實人物姓名或暗示虛構故事是真實案件。來源連結是研究線索，不代表其中每一項說法都已獨立證實；未知內容請明確當作未知，不要自行補成「真實細節」。
【本專案寫作 Skills 規範，生成時必須實際遵守】
{load_story_skill_guidance()}
故事用繁體中文，至少 1200 個中文字，分段清楚，有鋪陳、轉折和不安結尾。

【閱讀排版規則：重要交付要求】
1. content 是 HTML 片段，不是 Markdown，也不是完整 HTML 文件；不要把標籤包在程式碼區塊內。
2. title 欄位是故事主標題，由網站獨立顯示；正文不要再重複完整主標題。
3. 故事較長時，通常分成 3–6 個自然章節。因網站安全清理可能不保留標題標籤，章節標題請使用 <p><strong>第一章｜章節名稱</strong></p> 的形式；不要使用 h1-h6。
4. 每個一般敘事段落都必須使用 <p>...</p>，每段約 2–5 句為原則；避免一整頁只有一個大段落，也不要把每一句都拆成獨立段落。
5. 對白要有清楚的說話者區隔，重要對白可各自使用 <p class="dialogue">...</p>；不要把多位角色的對白擠在同一段。
6. 角色內心活動或特別語氣可使用 <em>；真正關鍵的線索可少量使用 <mark>；重要瞬間可少量使用 <strong>；日記、錄音、警方紀錄或文件摘錄可使用 <blockquote>。
7. 場景切換請用一個簡短的獨立段落呈現，例如 <p><em>—— 三小時後，地下室 ——</em></p>，避免使用可能被網站清理的分隔標籤。
8. 只可使用以下標籤：<p>、<strong>、<b>、<em>、<i>、<blockquote>、<br>、<span>、<mark>、<small>、<cite>、<q>、<ruby>、<rt>、<rp>。
9. 允許的屬性只有 class；可少量使用 class="dialogue"、class="eerie"、class="handwritten"、class="highlight"，不可依賴 class 才能理解內容。
10. 不得輸出 h1-h6、div、style、script、iframe、hr、img、CSS、JavaScript、任何 on* 事件屬性或完整 HTML 文件。所有標籤必須正確閉合。
11. 排版服務故事，不要為了視覺效果亂加粗、亂切段、濫用章節標題；節奏自然、適合手機連續閱讀。
純 JSON 格式：{{"title":"15至40字標題","subtitle":"頻道檔案副標題","slug":"lowercase-ascii-slug","summary":"80至160字摘要","content":"以 HTML 段落標籤排版的完整故事","director_analysis":{{"anomaly_core":"異常核心","character_core":"角色核心","internal_rule":"異常規則"}}}}"""
    errors=[]
    for provider in ("nvidia","agnes"):
        try:
            story,model=call_provider(provider,prompt,system)
            if not str(story.get("title","")).strip() or not str(story.get("content","")).strip(): raise RuntimeError("missing title/content")
            if len(story["content"])<900: raise RuntimeError(f"story too short ({len(story['content'])} chars)")
            slug=re.sub(r"[^a-z0-9-]+","-",str(story.get("slug") or story["title"].lower())).strip("-")[:70].strip("-") or "case-"+article["source_hash"]
            story["slug"]=slug; story["subtitle"]=str(story.get("subtitle") or c["channel"]+" 檔案 // 未知異常"); story["summary"]=str(story.get("summary") or story["content"][:160])
            story["director_analysis"]=story.get("director_analysis") if isinstance(story.get("director_analysis"),dict) else {}
            return story,provider,model
        except Exception as e:
            log(f"  {provider} failed: {e}"); errors.append(str(e))
    raise RuntimeError("all text providers failed: "+"; ".join(errors))

def generate_image_nvidia(prompt):

    """Generate with NVIDIA FLUX; detect content-filter responses and blank frames."""
    key=os.getenv("NVIDIA_API_KEY","")
    if not key: raise RuntimeError("NVIDIA_API_KEY missing")
    url="https://ai.api.nvidia.com/v1/genai/black-forest-labs/flux.1-dev"
    from PIL import Image, ImageStat
    last_error=None
    for attempt in range(2):
        # NVIDIA may return HTTP 200 even when the model did not generate an image.
        # Retry with a neutral, well-lit prompt rather than resending a potentially filtered prompt.
        current_prompt=prompt if attempt==0 else (
            "Create a clearly visible, richly detailed cinematic mystery illustration. "
            "A fictional scene for an atmospheric mystery archive, vivid teal and amber light, "
            "balanced exposure, detailed midtones, clearly visible objects and background, "
            "subtle suspense, elegant composition, high-quality film still. "
            "The image must not be blank, monochrome black, or underexposed. "
            "No text, no letters, no logo, no watermark. "
            + prompt[:700]
        )
        payload={"prompt":current_prompt,"mode":"base","seed":0 if attempt==0 else random.randint(1,2147483646),"steps":50,"cfg_scale":5.0,"width":1024,"height":1024,"samples":1}
        try:
            r=requests.post(url,headers={"Authorization":"Bearer "+key,"Accept":"application/json","Content-Type":"application/json"},json=payload,timeout=240)
            r.raise_for_status()
            data=r.json()
            artifacts=data.get("artifacts") or []
            artifact=artifacts[0] if artifacts else {}
            finish_reason=str(artifact.get("finishReason") or "UNKNOWN")
            if finish_reason.upper() not in ("SUCCESS","UNKNOWN"):
                raise RuntimeError("NVIDIA did not generate an image (finishReason="+finish_reason+", errorReason="+str(artifact.get("errorReason",""))+")")
            encoded=artifact.get("base64") or data.get("image") or data.get("image_base64")
            if not encoded: raise RuntimeError("NVIDIA response contains no image base64; keys="+str(list(data.keys())))
            if encoded.startswith("data:"): encoded=encoded.split(",",1)[1]
            raw=base64.b64decode(encoded,validate=True)
            im=Image.open(BytesIO(raw)).convert("RGB")
            im.thumbnail((1024,1024))
            stats=ImageStat.Stat(im)
            mean=sum(stats.mean)/3
            variation=sum(stats.stddev)/3
            if mean<7 or variation<3:
                raise RuntimeError(f"NVIDIA returned a blank/near-black frame (mean={mean:.1f}, variation={variation:.1f}, finishReason={finish_reason}, bytes={len(raw)})")
            out=BytesIO()
            im.save(out,format="WEBP",quality=88,method=6)
            result=out.getvalue()
            check=Image.open(BytesIO(result)).convert("RGB")
            stats=ImageStat.Stat(check)
            if sum(stats.mean)/3<7 or sum(stats.stddev)/3<3:
                raise RuntimeError("WebP validation detected a blank/near-black image")
            log(f"  Image accepted: {im.width}x{im.height}, {len(result)} bytes, finishReason={finish_reason}")
            return result
        except Exception as e:
            last_error=e
            log(f"  Image attempt {attempt+1}/2 failed: {e}")
            if attempt==0: time.sleep(2)
    raise RuntimeError(f"Image generation failed after retry: {last_error}")


def generate_image_agnes(prompt):
    """Use Agnes Image 2.5 Flash and return validated WebP bytes."""
    key=os.getenv("AGNES_API_KEY","")
    if not key: raise RuntimeError("AGNES_API_KEY missing")
    url="https://apihub.agnes-ai.com/v1/images/generations"
    model=os.getenv("AGNES_IMAGE_MODEL","agnes-image-2.5-flash")
    from PIL import Image, ImageStat
    last=None
    for attempt in range(2):
        try:
            payload={"model":model,"prompt":prompt,"n":1,"size":"1024x1024","extra_body":{"response_format":"url"}}
            r=requests.post(url,headers={"Authorization":"Bearer "+key,"Accept":"application/json","Content-Type":"application/json"},json=payload,timeout=300)
            if r.status_code in (429,500,502,503,504) and attempt==0:
                time.sleep(3)
                continue
            r.raise_for_status()
            items=r.json().get("data") or []
            item=items[0] if items else {}
            encoded=item.get("b64_json") or item.get("base64") or item.get("image")
            image_url=item.get("url") or item.get("image_url")
            if encoded:
                if encoded.startswith("data:"): encoded=encoded.split(",",1)[1]
                raw=base64.b64decode(encoded,validate=True)
            elif image_url:
                image_response=requests.get(image_url,timeout=120)
                image_response.raise_for_status()
                raw=image_response.content
            else: raise RuntimeError("Agnes response contains no usable image URL or base64")
            im=Image.open(BytesIO(raw)).convert("RGB")
            im.thumbnail((1024,1024))
            stats=ImageStat.Stat(im)
            if sum(stats.mean)/3<7 or sum(stats.stddev)/3<3: raise RuntimeError("Agnes returned a blank/near-black image")
            out=BytesIO()
            im.save(out,format="WEBP",quality=88,method=6)
            result=out.getvalue()
            check=Image.open(BytesIO(result)).convert("RGB")
            stats=ImageStat.Stat(check)
            if sum(stats.mean)/3<7 or sum(stats.stddev)/3<3: raise RuntimeError("Agnes WebP validation detected a blank image")
            log(f"  Agnes image accepted: {im.width}x{im.height}, {len(result)} bytes, model={model}")
            return result
        except Exception as e:
            last=e
            log(f"  Agnes image attempt {attempt+1}/2 failed: {e}")
            if attempt==0: time.sleep(2)
    raise RuntimeError(f"Agnes image generation failed after retry: {last}")

def generate_image(prompt):
    """Try Agnes first; use NVIDIA FLUX as a fallback."""
    try:
        return generate_image_agnes(prompt)
    except Exception as e:
        log(f"  Agnes failed; falling back to NVIDIA: {e}")
    return generate_image_nvidia(prompt)

def upload_image(filename,data):
    required=["FTP_HOST","FTP_USER","FTP_PASS","FTP_PATH","SITE_URL"]
    missing=[k for k in required if not os.getenv(k)]
    if missing: raise RuntimeError("missing FTP settings: "+", ".join(missing))
    ftp=FTP(os.environ["FTP_HOST"],timeout=45)
    try:
        ftp.login(os.environ["FTP_USER"],os.environ["FTP_PASS"])
        remote=os.environ["FTP_PATH"].strip("/")
        if remote: ftp.cwd(remote)
        ftp.storbinary("STOR "+filename,BytesIO(data))
    finally:
        try: ftp.quit()
        except Exception: pass
    site_url=re.sub(r"\s+","",os.environ["SITE_URL"].strip()).rstrip("/")
    return site_url+"/images/"+filename

def make_images(story,cat,dice):
    palette={"3":"warm candlelight, amber highlights, textured old paper","6":"phosphor green CRT glow, teal and amber lighting, analog surveillance monitors","9":"deep indigo atmosphere, restrained warning red accents, surreal geometric architecture"}[cat]
    prompts={"cover":f"Cinematic mystery archive cover, no text, no letters, no watermark. {palette}. Symbolic fictional scene inspired by {story['title']}. Clearly visible subject, balanced exposure, rich midtones, detailed shadows with visible texture, luminous highlights, not an all-black image. High-quality film still, square composition.",
             "scene":f"Cinematic mystery film still, no text, no letters, no watermark. {palette}. A key fictional scene inspired by {story['title']}. Fantasy level {dice['fantasy_level']}. Clearly visible characters and environment, balanced exposure, rich midtones, detailed shadows with visible texture, luminous highlights, not an all-black image. Square composition."}
    urls={"cover":"","scene":""}
    for kind,prompt in prompts.items():
        try:
            filename=f"{story['story_code']}_{kind}.webp"; urls[kind]=upload_image(filename,generate_image(prompt)); log("  Uploaded "+kind+" image")
        except Exception as e: log(f"  WARNING: {kind} image failed, story retained: {e}")
    return urls

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--date",default=(datetime.now(UTC)-timedelta(days=1)).strftime("%Y-%m-%d")); p.add_argument("--count",type=int,default=6)
    p.add_argument("--config"); p.add_argument("--providers"); p.add_argument("--channels"); p.add_argument("--content-dir",default="content"); p.add_argument("--skip-images",action="store_true")
    a=p.parse_args()
    datetime.strptime(a.date,"%Y-%m-%d")
    if not 1<=a.count<=12: raise SystemExit("--count must be 1..12")
    root=Path(a.content_dir); sd=root/"stories"; dd=root/"daily"; cd=root/"cases"; sd.mkdir(parents=True,exist_ok=True); dd.mkdir(parents=True,exist_ok=True); cd.mkdir(parents=True,exist_ok=True)
    log(f"CH-666 pipeline | date={a.date} | requested={a.count}")
    articles=fetch_story_sources(a.date,a.count,cd)
    if not articles: raise RuntimeError("No sourced news or historical cases returned; refusing to generate from mock data.")
    rng=random.SystemRandom(); cats=[rng.choice(["3","6","9"]) for _ in articles]
    counts={x:cats.count(x) for x in ("3","6","9")}
    log("Channel dice: "+", ".join(f"CH-{x*3}={counts[x]}" for x in ("3","6","9")))
    maxima={"3":0,"6":0,"9":0}
    for f in sd.glob("CH-*-*.json"):
        m=re.match(r"CH-(333|666|999)-(\d+)$",f.stem)
        if m:
            c={"333":"3","666":"6","999":"9"}[m.group(1)]; maxima[c]=max(maxima[c],int(m.group(2)))
    generated=[]; failed=0
    for i,article in enumerate(articles):
        if article.get("source_kind")=="historical_case":
            case_file=cd/("case_"+article["source_hash"]+".json")
            if not case_file.exists():
                case_record={"case_id":article["source_hash"],"title":article["source_title"],"source_url":article["source_url"],"source_summary":article.get("source_summary",""),"source_excerpt":article.get("source_content",""),"case_date":article.get("case_date",""),"source_kind":"historical_case","verification_note":"Research lead from linked source; facts and disputed details require source-level verification before factual reuse.","adaptable_elements":["investigation approach","clue pattern","timeline structure","unresolved question"],"created_at":now_iso()}
                case_file.write_text(json.dumps(case_record,ensure_ascii=False,indent=2),encoding="utf-8")
        cat=cats[i]; c=CHANNELS[cat]
        rr=random.Random(hashlib.sha256(f"{a.date}|{article['event_hash']}|{os.getenv('GITHUB_RUN_ID','manual')}".encode()).hexdigest())
        dice={"horror_score":rr.randint(20,98),"horror_type":rr.sample(c["types"],rr.randint(1,3)),"fantasy_level":rr.choice(c["fantasy"]),"narrative_style":rr.choice(c["styles"]),"pacing":rr.choice(PACINGS),"ending_type":rr.choice(ENDINGS),"perspective":rr.choice(PERSPECTIVES),"structure":rr.choice(["investigation_timeline","slow_reveal","unreliable_narrator","multiple_testimonies","found_document","reverse_chronology"]),"adaptation_mode":rr.choice(["inspired_by_method","inspired_by_clue","inspired_by_investigation","inspired_by_consequence","inspired_by_core_mystery"]),"reveal_density":rr.choice(["subtle","balanced","layered"]),"dice_seed":rr.randint(0,2**31-1)}
        # Conflict guard: avoid combinations that undermine the chosen story premise.
        if "crime" in dice["horror_type"] and dice["fantasy_level"]=="grounded" and dice["perspective"] in ("entity","object"):
            dice["perspective"]=rr.choice(["victim","witness","investigator"])
        if dice["narrative_style"] in ("police_report","interview_transcript") and dice["perspective"]=="entity":
            dice["perspective"]="witness"
        if dice["structure"]=="reverse_chronology" and dice["pacing"]=="slow_burn":
            dice["reveal_density"]="layered"
        log(f"[{i+1}/{len(articles)}] {c['channel']} | {article.get('source_kind','recent_news')} | {article['source_title'][:80]}")
        try:
            ai,provider,model=make_story(article,cat,dice); maxima[cat]+=1; code=f"CH-{cat*3}-{maxima[cat]:04d}"
            story={"story_code":code,"category":cat,"channel":c["channel"],"title":ai["title"],"subtitle":ai["subtitle"],"slug":ai["slug"],"summary":ai["summary"],"content":ai["content"],"horror_score":dice["horror_score"],"horror_type":dice["horror_type"],"fantasy_level":dice["fantasy_level"],"narrative_style":dice["narrative_style"],"pacing":dice["pacing"],"ending_type":dice["ending_type"],"perspective":dice["perspective"],"story_structure":dice["structure"],"adaptation_mode":dice["adaptation_mode"],"reveal_density":dice["reveal_density"],"source_kind":article.get("source_kind","recent_news"),"source_date":article["source_date"],"case_date":article.get("case_date",""),"source_hash":article["source_hash"],"event_hash":article["event_hash"],"source_url":article["source_url"],"provider_used":provider,"provider_model":model,"dice_seed":dice["dice_seed"],"director_analysis":ai["director_analysis"],"created_at":now_iso(),"cover_image":"","scene_images":""}
            if not a.skip_images:
                imgs=make_images(story,cat,dice); story["cover_image"]=imgs["cover"]; story["scene_images"]=imgs["scene"]
            story=clean_image_urls(story)
            (sd/f"{code}.json").write_text(json.dumps(story,ensure_ascii=False,indent=2),encoding="utf-8"); generated.append(story)
            log(f"  Saved {code}; content chars={len(story['content'])}")
        except Exception as e: failed+=1; log(f"  FAILED: {e}")
    generated=clean_image_urls(generated)
    payload={"date":a.date,"count":len(generated),"stories":generated,"generated_at":now_iso(),"channel_counts":counts}
    (dd/f"{a.date}.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    (dd/"latest.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    codes=",".join(s["story_code"] for s in generated); output({"generated_count":len(generated),"failed_count":failed,"story_codes":codes})
    log(f"Finished: generated={len(generated)}, failed={failed}, codes={codes or 'none'}")
    if not generated: raise RuntimeError("No stories generated successfully")

if __name__=="__main__":
    try: main()
    except Exception as e:
        log("FATAL: "+str(e)); output({"generated_count":0,"failed_count":1,"story_codes":""}); sys.exit(1)
