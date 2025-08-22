from pathlib import Path
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import csv
import re
import pandas as pd

HOMEPAGE = "https://ca.iaai.com/"
DETAIL_URL = "https://ca.iaai.com/vehicle-details/2753101"
STATE_FILE = "state.json"
OUTPUT_CSV = Path.cwd() / "auction_data.csv"
URLS_FILE = Path.cwd() / "urls.txt"

def load_urls(file_path: Path) -> list[str]:
    if not file_path.exists():
        return [DETAIL_URL]
    with open(file_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f]
    urls = [line for line in lines if line and not line.startswith("#")]
    return urls

# URLs are loaded from urls.txt so they are not hardcoded in code
URLS = load_urls(URLS_FILE)

HEADERS = [
    "Stock No",
    "Make",
    "Model",
    "Year",
    "Auction Date",
    "URL",
    "ACV Cost",
    "Repair Cost",
]


def clean_text(value: str) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def find_labeled_value(soup: BeautifulSoup, labels: list[str]) -> str:
    # Try to find text nodes that match any of the labels and read the nearby value
    label_pattern = re.compile(r"^\s*(" + "|".join([re.escape(l) for l in labels]) + r")\s*:?\s*$", re.IGNORECASE)

    # Strategy 1: dt/dd pairs
    for dt in soup.find_all("dt"):
        if dt.get_text(strip=True) and label_pattern.match(dt.get_text(strip=True)):
            dd = dt.find_next_sibling("dd")
            if dd:
                return clean_text(dd.get_text(" ", strip=True))

    # Strategy 2: label/value in adjacent siblings
    for tag in soup.find_all(string=label_pattern):
        parent = tag.parent
        if parent:
            # Next sibling
            sib = parent.find_next_sibling()
            if sib and clean_text(sib.get_text(" ", strip=True)):
                return clean_text(sib.get_text(" ", strip=True))
            # Parent's next element
            nxt = parent.find_next()
            if nxt and nxt is not parent and clean_text(nxt.get_text(" ", strip=True)):
                return clean_text(nxt.get_text(" ", strip=True))

    # Strategy 3: look for label within a div/span and get the following text in the same container
    for el in soup.find_all(["div", "span", "li", "p"]):
        txt = clean_text(el.get_text(" ", strip=True))
        for label in labels:
            if re.search(rf"\b{re.escape(label)}\b", txt, re.IGNORECASE):
                # Heuristic: remove the label part and take the remainder after colon
                after = re.split(rf"{re.escape(label)}\s*:?\s*", txt, flags=re.IGNORECASE)
                if len(after) > 1 and clean_text(after[1]):
                    return clean_text(after[1])
    return ""


def parse_vehicle(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    # Fallback stock from URL path (last numeric segment)
    stock_no = ""
    m = re.search(r"(\d{5,})", url)
    if m:
        stock_no = m.group(1)

    # Try to refine stock from page
    page_stock = find_labeled_value(soup, ["Stock No", "Stock#", "Stock Number", "Lot #", "Lot Number"]) or ""
    if page_stock:
        stock_no = page_stock

    # Make/Model/Year from title or labeled values
    title_text = clean_text(soup.title.get_text()) if soup.title else ""
    year = find_labeled_value(soup, ["Year"]) or ""
    make = find_labeled_value(soup, ["Make"]) or ""
    model = find_labeled_value(soup, ["Model"]) or ""

    if not (year and make and model) and title_text:
        mt = re.search(r"\b(19|20)\d{2}\b\s+([A-Za-z]+)\s+([A-Za-z0-9\- ]{2,})", title_text)
        if mt:
            year = year or mt.group(0).split()[0]
            if not make:
                make = mt.group(2)
            if not model:
                model = mt.group(3).strip()

    auction_date = find_labeled_value(soup, ["Auction Date", "Sale Date", "Auction Time", "Sale Time"]) or ""
    acv = find_labeled_value(soup, ["ACV", "Actual Cash Value"]) or ""
    repair = find_labeled_value(soup, ["Repair Cost", "Estimated Repair Cost", "Est. Repair"]) or ""

    # Normalize dollar formats if embedded in surrounding text
    money = re.compile(r"\$?\s?\d{1,3}(?:,\d{3})*(?:\.\d{2})?")
    acv_m = money.search(acv)
    if acv_m:
        acv = acv_m.group(0)
    repair_m = money.search(repair)
    if repair_m:
        repair = repair_m.group(0)

    return {
        "Stock No": clean_text(stock_no),
        "Make": clean_text(make),
        "Model": clean_text(model),
        "Year": clean_text(year),
        "Auction Date": clean_text(auction_date),
        "URL": url,
        "ACV Cost": clean_text(acv),
        "Repair Cost": clean_text(repair),
    }

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        args=["--disable-blink-features=AutomationControlled"],
    )

    context_kwargs = {
        "viewport": {"width": 1366, "height": 768},
        "locale": "en-US",
        "timezone_id": "America/Toronto",
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    }

    if Path(STATE_FILE).exists():
        context_kwargs["storage_state"] = STATE_FILE

    context = browser.new_context(**context_kwargs)

    context.add_init_script(
        """
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        Object.defineProperty(navigator, 'platform', { get: () => 'MacIntel' });
        window.chrome = { runtime: {} };
        """
    )

    page = context.new_page()

    # Warm-up on homepage to obtain cookies
    page.goto(HOMEPAGE, wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    try:
        page.get_by_role("button", name="Accept").click(timeout=1500)
    except Exception:
        pass

    rows: list[dict] = []
    for url in URLS:
        # Robust navigation: try domcontentloaded -> load -> manual wait
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
        except Exception:
            try:
                page.goto(url, wait_until="load", timeout=45000)
            except Exception:
                page.goto(url, timeout=60000)
                page.wait_for_timeout(2500)

        # Small human-like pause; scroll to trigger lazy content
        page.wait_for_timeout(1200)
        try:
            page.mouse.wheel(0, 1200)
        except Exception:
            pass
        page.wait_for_timeout(800)

        html = page.content()
        rows.append(parse_vehicle(html, url))

    # Save session for reuse
    context.storage_state(path=STATE_FILE)
    browser.close()

    # Write CSV
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    # Post-process with pandas: ensure column order, drop dupes, sort
    try:
        df = pd.read_csv(OUTPUT_CSV, dtype=str).fillna("")
        # enforce column order
        df = df[HEADERS]
        # normalize money columns (keep as strings)
        # drop duplicates by Stock No if present
        if "Stock No" in df.columns:
            df = df.drop_duplicates(subset=["Stock No"], keep="first")
        # sort by Auction Date then Stock No (string sort, okay for now)
        sort_cols = [c for c in ["Auction Date", "Stock No"] if c in df.columns]
        if sort_cols:
            df = df.sort_values(by=sort_cols, ascending=[True] * len(sort_cols))
        df.to_csv(OUTPUT_CSV, index=False)
    except Exception:
        # If pandas fails (e.g., file locked), leave the raw CSV
        pass