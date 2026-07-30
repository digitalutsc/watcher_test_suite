# lighthouse_helper.py
import csv
import aiohttp

STRATEGY = "desktop"  # or "mobile"
API_KEY = ""  # Optional, but recommended for large batches of URLs

def load_urls_from_csv(input_csv_path: str) -> list[str]:
    """Reads URLs from the first column of an input CSV file."""
    urls = []
    with open(input_csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, None)  # Skip header if present
        for row in reader:
            if row and row[0].strip():
                urls.append(row[0].strip())
    return urls

async def get_official_lighthouse_data(session: aiohttp.ClientSession, url: str) -> dict:
    endpoint = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
    
    categories = ["PERFORMANCE", "ACCESSIBILITY", "BEST_PRACTICES", "SEO"]
    params = [("url", url), ("strategy", STRATEGY)]
    for cat in categories:
        params.append(("category", cat))
    if API_KEY:
        params.append(("key", API_KEY))

    try:
        async with session.get(endpoint, params=params, timeout=120) as resp:
            if resp.status != 200:
                err_body = await resp.text()
                return {"url": url, "status": resp.status, "error": f"API Error: {err_body[:100]}"}
            
            data = await resp.json()
            lh = data.get("lighthouseResult", {})
            cats = lh.get("categories", {})
            audits = lh.get("audits", {})

            return {
                "url": url,
                "status": 200,
                # 4 Category Scores (0-100)
                "perf": int((cats.get("performance", {}).get("score") or 0) * 100),
                "a11y": int((cats.get("accessibility", {}).get("score") or 0) * 100),
                "bp": int((cats.get("best-practices", {}).get("score") or 0) * 100),
                "seo": int((cats.get("seo", {}).get("score") or 0) * 100),
                # Web Vitals & Lab Metrics
                "lcp_ms": round(audits.get("largest-contentful-paint", {}).get("numericValue", 0), 1),
                "cls": round(audits.get("cumulative-layout-shift", {}).get("numericValue", 0), 3),
                "ttfb_ms": round(audits.get("server-response-time", {}).get("numericValue", 0), 1),
                "tbt_ms": round(audits.get("total-blocking-time", {}).get("numericValue", 0), 1),
                "fcp_ms": round(audits.get("first-contentful-paint", {}).get("numericValue", 0), 1),
                "error": ""
            }
    except Exception as e:
        return {"url": url, "status": "Error", "error": str(e)}

def append_to_csv(data: dict, filepath: str):
    row = [
        data.get("url"),
        data.get("status"),
        data.get("perf", ""), data.get("a11y", ""), data.get("bp", ""), data.get("seo", ""),
        data.get("lcp_ms", ""), data.get("cls", ""), data.get("ttfb_ms", ""),
        data.get("tbt_ms", ""), data.get("fcp_ms", ""),
        data.get("error", "")
    ]
    with open(filepath, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(row)