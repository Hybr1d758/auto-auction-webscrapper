# auto-auction-webscrapper

## Auto Auction Web Scraper (Playwright + BeautifulSoup)

Scrapes IAAI vehicle detail pages, extracts key fields, and writes `auction_data.csv`.

### What it collects
- Stock No
- Make, Model, Year
- Auction Date
- URL (source)
- ACV Cost (Actual Cash Value)
- Repair Cost (Estimated Repair Cost)

### Project layout
- `webscrapper.py` – main script (Playwright navigation + BeautifulSoup parsing + pandas post-processing)
- `urls.txt` – one URL per line to scrape
- `auction_data.csv` – output CSV
- `.gitignore` – ignores venv, cache, artifacts
- `requirements.txt` – Python dependencies

### Prerequisites
- Python 3.9+
- macOS/Linux/Windows

### Setup
```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
python -m playwright install chromium --with-deps
```

### Usage
1) Put vehicle detail URLs in `urls.txt` (one per line).
2) Run the scraper (headless):
```bash
python webscrapper.py
```
3) Output appears at:
```
./auction_data.csv
```

Notes:
- Headless mode is enabled; no browser windows will open.
- If a site shows a WAF block, consider using a residential/ISP proxy and slower pacing.

### Options (change in code if needed)
- `URLS_FILE`: path to URLs list (defaults to `urls.txt`)
- `OUTPUT_CSV`: output path (defaults to `auction_data.csv` in CWD)

### GitHub: commit and push
```bash
git add webscrapper.py urls.txt requirements.txt .gitignore README.md
git commit -m "Scraper: Playwright + BS4; urls.txt; CSV output; README"
# set your remote if not already
# git remote add origin https://github.com/Hybr1d758/auto-auction-webscrapper.git
# push
git push -u origin main
```

### Troubleshooting
- Timeout on navigation: the script retries with different wait conditions.
- Still blocked: use a proxy and navigate from homepage → link → detail.
- SSL warning from urllib3: upgrade Python to an OpenSSL build or pin urllib3<2.
