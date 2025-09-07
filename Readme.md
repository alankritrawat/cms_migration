# CMS JSON Extractor POC

This project is a **CMS migration helper** that extracts structured JSON data from web pages or HTML files. It uses an **LLM (Large Language Model)** to classify content into CMS models (banner, headline, teaser) and organizes them into **nested page JSON** and **atomic model JSONs**. The Streamlit UI allows single and bulk extraction with **ZIP downloads**.

---

## Features

- Extracts **meta tags** and **DOM snippets** from web pages or HTML files.
- Uses **LLM** to classify content into CMS models.
- Generates **nested page JSON** and **atomic model JSONs**.
- Supports **single URL, bulk URLs, single HTML, and bulk HTML** extraction.
- Streamlined **UI with tabs, collapsible JSON display, and ZIP downloads**.
- Handles **empty pages** by generating fallback JSON.

---

## Project Structure

```
cms-json-extractor/
│
├─ backend/
│   └─ extractor.py        # Main extraction script
│
├─ app.py                  # Streamlit UI
├─ pages/                  # Nested page JSON output
├─ models/                 # Model JSON output
├─ urls.txt                # Optional test URLs
└─ README.md
```

---

## Setup Instructions

### 1️⃣ Create a new Python environment

```bash
python -m venv myenv
```

Activate the environment:

- **Windows:**
```bash
myenv\Scripts\activate
```
- **Mac/Linux:**
```bash
source myenv/bin/activate
```

---

### 2️⃣ Install dependencies

```bash
pip install --upgrade pip
pip install streamlit beautifulsoup4 playwright ollama requests json5
```

**Install Playwright browsers:**

```bash
playwright install
```

---

### 3️⃣ Setup project folders

The script automatically creates:

```
pages/
models/
```

If needed, create them manually:

```bash
mkdir pages models
```

---

### 4️⃣ Configure LLM (Ollama)

- Make sure **Ollama** is installed and running.
- The backend uses **`gemma:2b`** model by default (`LLM_MODEL="gemma:2b"`).
- To disable LLM, set `USE_LLM = False` in `extractor.py`.

---

## Usage

### 1️⃣ Run Streamlit App

```bash
streamlit run app.py
```

Open the displayed URL in your browser (usually `http://localhost:8501`).

### 2️⃣ Single URL Extraction

- Go to **“Single URL” tab**.
- Enter a URL.
- Click **Extract Single URL**.
- View **Nested Page JSON** and **Model JSONs** in expandable sections.
- Download a **ZIP** containing page + models.

### 3️⃣ Bulk URL Extraction

- Go to **“Bulk URLs (.txt)” tab**.
- Upload a `.txt` file containing one URL per line.
- Click **Extract Bulk URLs**.
- Each URL generates collapsible **page + model JSON**.
- Download ZIPs for each page.

### 4️⃣ Single HTML File Extraction

- Go to **“Single HTML File” tab**.
- Upload a `.html` file.
- Click **Extract Single HTML**.
- JSON previews and ZIP download are available.

### 5️⃣ Bulk HTML Extraction

- Go to **“Bulk HTML Files” tab**.
- Upload a `.zip` containing multiple HTML files.
- Each file is processed individually with JSON previews.
- ZIP downloads are available per page.

---

## Backend Workflow

1. **Fetch HTML** using Playwright (Firefox first, fallback to Chromium).
2. **Parse HTML** with BeautifulSoup.
3. **Extract meta tags** (title, description, canonical, og:, twitter:).
4. **Extract DOM snippets** (hero/banner, headings, main paragraphs, card-like elements).
5. **Call LLM** to classify snippets into CMS models:
    - `banner`
    - `headline`
    - `teaser`
6. **Write JSON files**:
    - `pages/<slug>.json` → nested page JSON
    - `models/<slug>/*.json` → individual model JSONs

---

## JSON Output Example

**Nested Page JSON (`pages/example-page.json`):**

```json
{
  "page_url": "https://example.com/",
  "page_uid": "page_example-page",
  "models": [
    {"type": "banner", "path": "models/example-page/banner_001.json"},
    {"type": "headline", "path": "models/example-page/headline_001.json"}
  ],
  "metadata": {
    "title": "Example Domain",
    "description": ""
  }
}
```

**Model JSON (`models/example-page/banner_001.json`):**

```json
{
  "Title": "Example Domain",
  "url": "https://example.com/image.jpg",
  "alt": "Example Banner",
  "Headline": "",
  "Byline": "",
  "Description": "This is an example page"
}
```

---

## Notes & Tips

- **Empty pages** generate fallback JSON to prevent failures.
- **Bulk extraction** may take time depending on network and number of pages.
- **Collapsible JSON** in Streamlit improves readability for large outputs.
- Make sure **LLM (Ollama) is running** for content classification.

