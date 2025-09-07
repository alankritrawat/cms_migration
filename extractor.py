"""
Robust CMS JSON Extractor (URL + HTML)
- Captures meta + DOM snippets
- Delegates schema classification to LLM
- Always creates at least one model per snippet
- Writes atomic model JSONs and nested page JSON
"""

import sys, json, re, pathlib, io
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import ollama
from playwright.sync_api import sync_playwright

# Force UTF-8 output
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# === Config ===
USE_LLM = True
LLM_MODEL = "gemma:2b"
OUT_DIR = pathlib.Path(__file__).resolve().parent.parent
PAGES_DIR = OUT_DIR / "pages"
MODELS_DIR = OUT_DIR / "models"

for d in (PAGES_DIR, MODELS_DIR):
    d.mkdir(parents=True, exist_ok=True)

# === Helpers ===
def slugify(url_or_name: str) -> str:
    """Safe folder/filename for Windows"""
    slug = re.sub(r'[^a-z0-9]+', '-', url_or_name.strip().lower())
    slug = re.sub(r'-+', '-', slug)
    return slug.strip('-') or "page"

def get_html(source: str) -> str:
    """Fetch HTML from URL or local file"""
    from pathlib import Path
    if Path(source).exists():
        return Path(source).read_text(encoding="utf-8")

    with sync_playwright() as p:
        for browser_type in [p.firefox, p.chromium]:
            try:
                browser = browser_type.launch(headless=True)
                page = browser.new_page()
                page.goto(source, timeout=180000, wait_until="load")
                page.wait_for_load_state("networkidle", timeout=60000)
                html = page.content()
                browser.close()
                return html
            except:
                browser.close()
                continue
    raise RuntimeError(f"Could not fetch HTML from {source}")

def soupify(html: str):
    return BeautifulSoup(html, "html.parser")

def extract_meta(soup):
    meta = {}
    head = soup.find("head")
    if head:
        for t in head.find_all("meta"):
            if t.get("property"): meta[t["property"].strip()] = t.get("content","").strip()
            elif t.get("name"): meta[t["name"].strip()] = t.get("content","").strip()
        t = head.find("title")
        if t and t.string: meta.setdefault("title", t.string.strip())
        can = head.find("link", {"rel": "canonical"})
        if can and can.get("href"): meta.setdefault("canonical", can["href"].strip())
    return meta

def extract_snippets(soup, max_blocks=15):
    snippets = []
    # Common blocks
    for sel in ["header",".hero",".banner","main","article","section",".card",".teaser",".tile"]:
        el = soup.select_one(sel)
        if el:
            text = el.get_text(" ", strip=True)
            if text:
                snippets.append({"selector": sel, "text": text[:2000]})
    # Headings
    for h in ["h1","h2","h3","h4"]:
        el = soup.select_one(h)
        if el and el.get_text(strip=True):
            snippets.append({"selector": h, "text": el.get_text(" ",strip=True)[:600]})
    # Paragraphs
    for main_sel in ["main","article","section"]:
        main = soup.select_one(main_sel)
        if main:
            for p in main.find_all("p", limit=5):
                text = p.get_text(" ", strip=True)
                if text:
                    snippets.append({"selector": f"{main_sel} > p", "text": text[:800]})
    # Deduplicate & limit
    unique, seen = [], set()
    for s in snippets:
        key = s.get("selector")+":"+s.get("text","")[:80]
        if key not in seen: unique.append(s); seen.add(key)
        if len(unique) >= max_blocks: break
    return unique

# --- Prompt template ---
PROMPT_TEMPLATE = """
You are an expert CMS migration assistant. You will be given:

1) A dictionary of meta tags (og:, twitter:, description, title, canonical, etc. etc.)
2) A list of page snippets (candidate blocks) extracted from the DOM.

Task:
- Identify which snippets/meta entries should be used to construct CMS "models". We support model types:
  1) banner  --> fields: Title, url, alt, width, height, Headline, Byline, Description
  2) headline --> fields: headline_text, color (enum: black, white, red, blue), content_type_uid
  3) teaser --> fields: title, description, image, alt_text, display_type (enum: compact, large, image_left, image_right), uid
  4) If you found any other types please add the same

Rules:
- Output JSON only (no explanation). The top-level must be an object:
  {
    "page": {"page_url": "<url>", "page_title": "<title>"},
    "models": [ { "type": "<banner|headline|teaser|others>", "fields": {...} }, ... ]
  }
- Each model's fields must match schema exactly. Use empty string "" if missing.
- Prefer meta tags for banner image/title/description; use DOM snippets if missing.
- Generate concise alt_text if missing.
- Clean headlines (remove suffixes like " | Brand").
- Summarize long text into <=160 chars for descriptions.

NOTE:
Return ONLY valid JSON. 
Do not add comments, explanations, or markdown. 
Make sure it parses with json.loads in Python without errors.
"""

def safe_json_parse(raw: str):
    if raw.startswith("```"): raw = raw.strip("`\n"); 
    if raw.lower().startswith("json"): raw = raw[4:].strip()
    try: return json.loads(raw)
    except: pass
    match = re.search(r"\{.*\}", raw, re.S)
    if match:
        try: return json.loads(match.group(0))
        except: pass
    try:
        import json5
        return json5.loads(raw)
    except: raise RuntimeError(f"❌ Could not parse JSON:\n{raw[:500]}")

def call_llm(meta_dict: dict, snippets: list, page_url: str) -> dict:
    if not USE_LLM: raise RuntimeError("LLM disabled")
    data = {"meta": meta_dict, "snippets": snippets, "page_url": page_url}
    try:
        resp = ollama.chat(
            model=LLM_MODEL,
            messages=[{"role":"system","content":PROMPT_TEMPLATE},
                      {"role":"user","content":json.dumps(data, ensure_ascii=False)}]
        )
        parsed = safe_json_parse(resp["message"]["content"].strip())
    except Exception as e:
        print(f"⚠️ LLM call failed: {e}, using fallback models")
        parsed = {"page":{"page_url":page_url,"page_title":meta_dict.get("title","N/A")}, "models":[]}

    # Ensure at least one model per snippet
    if "models" not in parsed or not parsed["models"]:
        parsed["models"] = []
        for idx, s in enumerate(snippets):
            parsed["models"].append({
                "type": "custom_block",
                "fields": {
                    "title": s.get("text","")[:60],
                    "description": s.get("text","")[:160],
                    "image": "",
                    "url": page_url
                }
            })
    return parsed

def write_models_to_files(models_obj, slug):
    page_dir = MODELS_DIR / slug
    page_dir.mkdir(parents=True, exist_ok=True)
    written = []
    counters = {}
    for m in models_obj.get("models", []):
        t = m.get("type","model")
        counters.setdefault(t,0); counters[t]+=1
        fname = f"{t}_{counters[t]:03d}.json"; fpath = page_dir / fname
        with open(fpath,"w",encoding="utf-8") as fh: json.dump(m.get("fields",{}), fh, ensure_ascii=False, indent=2)
        written.append({"type":t,"path":str(fpath.relative_to(OUT_DIR))})
    page_json = {
        "page_url": models_obj.get("page",{}).get("page_url",""),
        "page_uid": f"page_{slug}",
        "models": written,
        "metadata": {"title": models_obj.get("page",{}).get("page_title","N/A"),"description":""}
    }
    page_file = PAGES_DIR / f"{slug}.json"
    with open(page_file,"w",encoding="utf-8") as fh: json.dump(page_json, fh, ensure_ascii=False, indent=2)
    return page_json

def build_models_for_page(source: str):
    slug = slugify(source)
    html = get_html(source)
    if not html.strip():
        dummy = {"page_url": source, "page_uid": f"page_{slug}", "models": [], "metadata":{"title":"N/A","description":""}}
        page_file = PAGES_DIR / f"{slug}.json"
        with open(page_file,"w",encoding="utf-8") as fh: json.dump(dummy, fh, ensure_ascii=False, indent=2)
        return dummy
    soup = soupify(html)
    meta = extract_meta(soup)
    snippets = extract_snippets(soup,max_blocks=15)
    if not meta and not snippets:
        dummy = {"page_url": source, "page_uid": f"page_{slug}", "models": [], "metadata":{"title":"N/A","description":""}}
        return write_models_to_files(dummy, slug)
    try:
        models_obj = call_llm(meta,snippets,source)
    except Exception as e:
        print(f"⚠️ LLM failed for {source}: {e}, creating dummy JSON")
        models_obj = {"page":{"page_url":source,"page_title":"N/A"},"models":[]}
    return write_models_to_files(models_obj, slug)

# --- CLI ---
if __name__ == "__main__":
    sources = [a for a in sys.argv[1:] if a != "--local"]
    for s in sources:
        print(f"Processing: {s}")
        try:
            out = build_models_for_page(s)
            print(json.dumps(out, indent=2, ensure_ascii=False))
        except Exception as e:
            print(f"❌ Extraction failed for {s}: {e}")
