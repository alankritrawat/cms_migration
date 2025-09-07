import streamlit as st
import subprocess, sys, json, pathlib, zipfile, io

# -----------------------------
# Folders
# -----------------------------
OUT_DIR = pathlib.Path(".").resolve()
MODELS_DIR = OUT_DIR / "models"
PAGES_DIR = OUT_DIR / "pages"
for d in (PAGES_DIR, MODELS_DIR):
    d.mkdir(parents=True, exist_ok=True)

# -----------------------------
# Custom CSS
# -----------------------------
st.markdown("""
    <style>
        .css-1v3fvcr {font-size:22px; font-weight:500;}  
        .css-1d391kg {font-size:18px; font-weight:400;}  
        .stButton>button {font-size:16px; padding:8px 16px;}  
        .stTextInput>div>div>input {font-size:16px;}  
    </style>
""", unsafe_allow_html=True)

st.set_page_config(page_title="CMS JSON Extractor", layout="wide")
st.title("📄 CMS JSON Extractor POC")

# -----------------------------
# Debug Mode Toggle
# -----------------------------
debug_mode = st.checkbox("🛠️ Debug Mode: Show meta tags & snippets", value=False)

# -----------------------------
# Utility Functions
# -----------------------------
def process_source(source: str, label: str = "Processing"):
    st.info(f"{label} {source} ...")
    try:
        result = subprocess.run(
            [sys.executable, "backend/extractor.py", source],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        stdout = result.stdout.decode("utf-8", errors="replace")
        stderr = result.stderr.decode("utf-8", errors="replace")

        if result.returncode != 0:
            st.error(f"❌ Extractor failed:\n{stderr}")
            return None, None, None, None

        # Parse backend JSON output for slug
        try:
            page_obj = json.loads(stdout)
            slug = page_obj.get("page_uid", "page_unknown").replace("page_", "")
        except Exception:
            slug = source.strip("/").split("/")[-1].replace(".html", "")
            page_obj = None

        page_file = PAGES_DIR / f"{slug}.json"

        # Initialize fallback JSON
        if not page_file.exists():
            dummy = {
                "page_url": source,
                "page_uid": f"page_{slug}",
                "models": [],
                "metadata": {"title": "N/A", "description": ""}
            }
            with open(page_file, "w", encoding="utf-8") as f:
                json.dump(dummy, f, ensure_ascii=False, indent=2)
            page_obj = dummy
        elif page_obj is None:
            with open(page_file, "r", encoding="utf-8") as f:
                page_obj = json.load(f)

        # --- Debug info ---
        meta_info = None
        snippets_info = None
        if debug_mode:
            try:
                import backend.extractor as ext
                html_content = ext.get_html(source)
                soup = ext.soupify(html_content)
                meta_info = ext.extract_meta(soup)
                snippets_info = ext.extract_snippets(soup)
            except Exception as e:
                st.warning(f"⚠️ Could not fetch debug info: {e}")

        return slug, page_obj, meta_info, snippets_info
    except Exception as e:
        st.error(f"❌ Extraction failed: {e}")
        return None, None, None, None

def display_json_and_zip(slug: str, page_obj: dict, meta_info=None, snippets_info=None):
    if debug_mode:
        if meta_info:
            with st.expander("🛠 Meta Tags (Debug)"):
                st.json(meta_info)
        if snippets_info:
            with st.expander("🛠 DOM Snippets (Debug)"):
                st.json(snippets_info)

    with st.expander("📑 Nested Page JSON"):
        st.json(page_obj)
    with st.expander("🗂 Models JSON"):
        for model in page_obj.get("models", []):
            st.json(model)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        page_file = PAGES_DIR / f"{slug}.json"
        zf.write(page_file, arcname=page_file.name)
        model_dir = MODELS_DIR / slug
        if model_dir.exists():
            for mf in model_dir.glob("*.json"):
                zf.write(mf, arcname=f"{slug}/{mf.name}")

    st.download_button(
        label="⬇️ Download ZIP",
        data=zip_buffer.getvalue(),
        file_name=f"{slug}.zip",
        mime="application/zip",
        key=f"zip_{slug}"
    )

# -----------------------------
# Tabs
# -----------------------------
tab_url, tab_bulk_url, tab_html, tab_bulk_html = st.tabs([
    "Single URL", "Bulk URLs (.txt)", "Single HTML File", "Bulk HTML Files"
])

# -----------------------------
# Single URL Tab
# -----------------------------
with tab_url:
    st.header("🔗 Extract JSON from URL")
    url_input = st.text_input("Enter full URL (include https://)")
    if st.button("⚡ Extract Single URL"):
        if url_input.strip():
            slug, page_obj, meta_info, snippets_info = process_source(url_input)
            if slug and page_obj:
                display_json_and_zip(slug, page_obj, meta_info, snippets_info)

# -----------------------------
# Bulk URLs Tab
# -----------------------------
with tab_bulk_url:
    st.header("📂 Extract JSON from URL List (.txt)")
    uploaded_file = st.file_uploader("Upload a .txt file with URLs (one per line)", type=["txt"])
    if uploaded_file and st.button("⚡ Extract Bulk URLs"):
        urls = [line.strip() for line in uploaded_file.read().decode("utf-8").splitlines() if line.strip()]
        st.info(f"Processing {len(urls)} URLs ...")
        for idx, url in enumerate(urls, start=1):
            st.subheader(f"{idx}. {url}")
            slug, page_obj, meta_info, snippets_info = process_source(url)
            if slug and page_obj:
                display_json_and_zip(slug, page_obj, meta_info, snippets_info)

# -----------------------------
# Single HTML File Tab
# -----------------------------
with tab_html:
    st.header("📄 Extract JSON from Local HTML File")
    html_file = st.file_uploader("Upload a single HTML file", type=["html"])
    if html_file and st.button("⚡ Extract Single HTML"):
        path = pathlib.Path(html_file.name)
        with open(path, "wb") as f:
            f.write(html_file.getbuffer())
        slug, page_obj, meta_info, snippets_info = process_source(str(path), label=html_file.name)
        if slug and page_obj:
            display_json_and_zip(slug, page_obj, meta_info, snippets_info)

# -----------------------------
# Bulk HTML Tab
# -----------------------------
with tab_bulk_html:
    st.header("📂 Extract JSON from Multiple HTML Files")
    st.info("Upload multiple HTML files as .zip (one HTML per file)")
    bulk_html_zip = st.file_uploader("Upload .zip containing HTML files", type=["zip"])
    if bulk_html_zip and st.button("⚡ Extract Bulk HTML"):
        zip_path = pathlib.Path("temp_bulk.zip")
        with open(zip_path, "wb") as f:
            f.write(bulk_html_zip.getbuffer())
        with zipfile.ZipFile(zip_path, "r") as zf:
            file_list = zf.namelist()
            st.info(f"Found {len(file_list)} files in ZIP")
            for html_file in file_list:
                with zf.open(html_file) as f:
                    out_file = pathlib.Path(html_file)
                    out_file.write_bytes(f.read())
                    st.subheader(f"{html_file}")
                    slug, page_obj, meta_info, snippets_info = process_source(str(out_file), label=html_file)
                    if slug and page_obj:
                        display_json_and_zip(slug, page_obj, meta_info, snippets_info)
