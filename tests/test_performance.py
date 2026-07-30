# tests/test_performance.py
import os
import sys
import csv
import ssl
import certifi
import asyncio
import aiohttp
import statistics
import random
from datetime import datetime

# Add root folder to sys.path so config imports cleanly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings

csv_write_lock = asyncio.Lock()

NUM_BENCHMARK_PASSES = 2


def get_dynamic_output_path():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(settings.PERF_OUTPUT_DIR, f"test_performance_averaged_{timestamp}.csv")


async def fetch_pagespeed_single_pass(session, url, worker_prefix, max_retries=2):
    """Executes a single PageSpeed Insights API call."""
    endpoint = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
    
    categories = ["PERFORMANCE", "ACCESSIBILITY", "BEST_PRACTICES", "SEO"]
    params = [
        ("url", url),
        ("strategy", settings.PERF_STRATEGY)
    ]
    for cat in categories:
        params.append(("category", cat))
    
    if settings.PERF_API_KEY:
        params.append(("key", settings.PERF_API_KEY))

    for attempt in range(1, max_retries + 2):
        try:
            async with session.get(endpoint, params=params, timeout=120) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    lh = data.get("lighthouseResult", {})
                    cats = lh.get("categories", {})
                    audits = lh.get("audits", {})

                    return 200, {
                        "perf": int((cats.get("performance", {}).get("score") or 0) * 100),
                        "a11y": int((cats.get("accessibility", {}).get("score") or 0) * 100),
                        "bp": int((cats.get("best-practices", {}).get("score") or 0) * 100),
                        "seo": int((cats.get("seo", {}).get("score") or 0) * 100),
                        "lcp": round(audits.get("largest-contentful-paint", {}).get("numericValue", 0), 1),
                        "cls": round(audits.get("cumulative-layout-shift", {}).get("numericValue", 0), 3),
                        "ttfb": round(audits.get("server-response-time", {}).get("numericValue", 0), 1),
                        "tbt": round(audits.get("total-blocking-time", {}).get("numericValue", 0), 1),
                        "fcp": round(audits.get("first-contentful-paint", {}).get("numericValue", 0), 1),
                    }, ""

                elif resp.status in (500, 502, 503, 504) and attempt <= max_retries:
                    print(f"   {worker_prefix} ⚠️ API Status {resp.status}. Retrying (Attempt {attempt}/{max_retries})...")
                    await asyncio.sleep(3 * attempt)
                    continue
                else:
                    err_text = await resp.text()
                    return resp.status, {}, f"API Error {resp.status}: {err_text[:120]}"

        except Exception as e:
            if attempt <= max_retries:
                await asyncio.sleep(3 * attempt)
                continue
            return "Error", {}, str(e)

    return "Error", {}, "Max retries exceeded"


async def warmup_and_fetch_cold_score(session, url, worker_prefix):
    """Warms up the server/cache and captures the initial cold performance score."""
    print(f"   {worker_prefix} 🔥 Warming server cache & capturing cold performance for: {url}")
    
    # Send quick direct request to trigger web server/database caching
    try:
        async with session.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"}) as warmup_resp:
            await warmup_resp.read()
    except Exception:
        pass

    # Fetch initial PageSpeed performance score (Cold run)
    status, metrics, _ = await fetch_pagespeed_single_pass(session, url, f"{worker_prefix} [Cold-Run]")
    cold_perf_score = metrics.get("perf", "") if status == 200 else "N/A"
    
    await asyncio.sleep(1.0)
    return cold_perf_score


async def fetch_averaged_pagespeed_metrics(session, url, worker_prefix):
    """Handles cold-pass capture and averages metrics across benchmark passes."""
    
    # Capture initial cold performance score
    cold_perf_score = await warmup_and_fetch_cold_score(session, url, worker_prefix)

    pass_results = []
    last_error = ""

    for pass_num in range(1, NUM_BENCHMARK_PASSES + 1):
        print(f"   {worker_prefix} ⚡ Benchmark Pass {pass_num}/{NUM_BENCHMARK_PASSES} for: {url}")
        status, metrics, error = await fetch_pagespeed_single_pass(session, url, worker_prefix)
        
        if status == 200:
            pass_results.append(metrics)
        else:
            last_error = error
            
        if pass_num < NUM_BENCHMARK_PASSES:
            await asyncio.sleep(2.0)

    if not pass_results:
        return "Error", cold_perf_score, {}, last_error or "All benchmark passes failed"

    averaged_metrics = {
        "perf": round(statistics.mean([p["perf"] for p in pass_results])),
        "a11y": round(statistics.mean([p["a11y"] for p in pass_results])),
        "bp": round(statistics.mean([p["bp"] for p in pass_results])),
        "seo": round(statistics.mean([p["seo"] for p in pass_results])),
        "lcp": round(statistics.mean([p["lcp"] for p in pass_results]), 1),
        "cls": round(statistics.mean([p["cls"] for p in pass_results]), 3),
        "ttfb": round(statistics.mean([p["ttfb"] for p in pass_results]), 1),
        "tbt": round(statistics.mean([p["tbt"] for p in pass_results]), 1),
        "fcp": round(statistics.mean([p["fcp"] for p in pass_results]), 1),
    }

    return 200, cold_perf_score, averaged_metrics, ""


async def perf_worker(worker_id, queue, session, output_file_path):
    while not queue.empty():
        idx, original_url = await queue.get()
        worker_prefix = f"[Worker {worker_id}] [{idx}]"

        http_status, cold_perf, res, error_details = await fetch_averaged_pagespeed_metrics(session, original_url, worker_prefix)

        async with csv_write_lock:
            with open(output_file_path, "a", newline="", encoding="utf-8") as f_out:
                writer = csv.writer(f_out)
                writer.writerow([
                    original_url,                          # 0: URL
                    http_status,                            # 1: HTTP Status
                    cold_perf,                              # 2: Initial Perf Score (Cold)
                    res.get("perf", ""),                    # 3: Performance Score (Averaged)
                    res.get("a11y", ""),                    # 4: Accessibility Score
                    res.get("bp", ""),                      # 5: Best Practices Score
                    res.get("seo", ""),                     # 6: SEO Score
                    res.get("lcp", ""),                     # 7: Largest Contentful Paint (ms)
                    res.get("cls", ""),                     # 8: Cumulative Layout Shift
                    res.get("ttfb", ""),                    # 9: Time to First Byte (ms)
                    res.get("tbt", ""),                     # 10: Total Blocking Time (ms)
                    res.get("fcp", ""),                     # 11: First Contentful Paint (ms)
                    error_details                           # 12: Error Details
                ])

        if http_status == 200:
            print(
                f"{worker_prefix} ✅ Scores -> Cold Perf: {cold_perf} | Avg Perf: {res['perf']} | "
                f"A11y: {res['a11y']} | BP: {res['bp']} | SEO: {res['seo']} | LCP: {res['lcp']}ms"
            )
        else:
            print(f"{worker_prefix} ❌ Failed -> {error_details}")

        await asyncio.sleep(random.uniform(1.0, 2.0))
        queue.task_done()


async def run_performance_tests():
    os.makedirs(settings.PERF_OUTPUT_DIR, exist_ok=True)

    if not os.path.exists(settings.PERF_INPUT_FILE):
        print(f"❌ Error: Input CSV not found at '{settings.PERF_INPUT_FILE}'")
        return

    urls_list = []
    with open(settings.PERF_INPUT_FILE, "r", encoding="utf-8") as f_in:
        reader = csv.reader(f_in)
        next(reader, None)
        for row in reader:
            if row and row[0].strip():
                urls_list.append(row[0].strip())

    if not urls_list:
        print("❌ No URLs found in input CSV.")
        return

    output_file_path = get_dynamic_output_path()
    print(f"\n==========================================")
    print(f"⚡ WATCHER PAGESPEED PERFORMANCE AUDITOR")
    print(f"==========================================")
    print(f"Total URLs: {len(urls_list)}")
    print(f"Strategy: {settings.PERF_STRATEGY}")
    print(f"API Key Detected: {'Yes' if settings.PERF_API_KEY else 'No (Unauthenticated)'}")
    print(f"Output CSV: {output_file_path}\n")

    # Header structure cleanly aligned with writer row indices
    headers = [
        "URL", 
        "HTTP Status",
        "Initial Perf Score (Cold)",
        "Performance Score", 
        "Accessibility Score", 
        "Best Practices Score", 
        "SEO Score",
        "Largest Contentful Paint (ms)",
        "Cumulative Layout Shift",
        "Time to First Byte (ms)",
        "Total Blocking Time (ms)",
        "First Contentful Paint (ms)",
        "Error Details"
    ]
    
    with open(output_file_path, "w", newline="", encoding="utf-8") as f_out:
        writer = csv.writer(f_out)
        writer.writerow(headers)

    queue = asyncio.Queue()
    for idx, url in enumerate(urls_list, 1):
        await queue.put((idx, url))

    max_workers = min(settings.CONCURRENT_WORKERS, 2)
    
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    connector = aiohttp.TCPConnector(ssl=ssl_context)

    async with aiohttp.ClientSession(connector=connector) as session:
        workers = [
            asyncio.create_task(perf_worker(i, queue, session, output_file_path))
            for i in range(max_workers)
        ]

        await queue.join()

        for w in workers:
            w.cancel()

    # Append Executive Glossary
    with open(output_file_path, "a", newline="", encoding="utf-8") as f_out:
        writer = csv.writer(f_out)
        writer.writerow([])
        writer.writerow(["--- PERFORMANCE METRICS GLOSSARY & TARGETS ---"])
        writer.writerow(["Metric", "Target", "Plain English Definition"])
        writer.writerow(["Initial Perf Score (Cold)", "90 - 100", "Performance score captured before server database/asset caches are primed."])
        writer.writerow(["Performance Score", "90 - 100", "Averaged score measuring how fast and responsive the page feels when warm."])
        writer.writerow(["Accessibility Score", "90 - 100", "Measures how usable the site is for users with disabilities or screen readers."])
        writer.writerow(["Best Practices Score", "90 - 100", "Checks modern web standards, HTTPS security, and clean code implementation."])
        writer.writerow(["SEO Score", "90 - 100", "Evaluates how easily search engines can crawl, understand, and index the page."])
        writer.writerow(["Largest Contentful Paint (LCP)", "< 2.5 sec", "Time taken for the primary visual content (e.g. main banner or text) to appear."])
        writer.writerow(["Cumulative Layout Shift (CLS)", "< 0.1", "Visual stability check: measures if layout elements jump around while loading."])
        writer.writerow(["Time to First Byte (TTFB)", "< 0.8 sec", "Server responsiveness: speed at which the server responds to the browser request."])
        writer.writerow(["Total Blocking Time (TBT)", "< 0.2 sec", "Interactivity delay: total time page is frozen/unresponsive to user clicks."])
        writer.writerow(["First Contentful Paint (FCP)", "< 1.8 sec", "Time until the very first piece of text, logo, or visual element appears on screen."])

    print(f"\n✅ Performance test run complete. Saved to: {output_file_path}")


if __name__ == "__main__":
    asyncio.run(run_performance_tests())