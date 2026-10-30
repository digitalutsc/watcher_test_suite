# tests/test_search.py
import os
import sys
import csv
import random
import asyncio
from datetime import datetime
from urllib.parse import urljoin, quote_plus

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from src.browser import BrowserManager

csv_write_lock = asyncio.Lock()


def get_dynamic_output_path():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(settings.SEARCH_OUTPUT_DIR, f"test_search_output_{timestamp}.csv")


async def execute_search(page, site_url, search_term, worker_prefix):
    """
    Navigates to /search-results, fills the search input, submits the form via UI/Enter,
    and extracts total result count + individual item links.
    """
    search_page_url = f"{site_url.rstrip('/')}/search-results"
    print(f"   {worker_prefix} 1/3 Navigating to search page: {search_page_url}")
    
    try:
        response = await page.goto(search_page_url, wait_until="networkidle", timeout=30000)
        if response and response.status >= 400:
            return "Failed", 0, [], f"HTTP Error {response.status}"
    except Exception as e:
        return "Failed", 0, [], f"Navigation error: {str(e).split('\n')[0]}"

    # 1. Interact with the Search Form UI
    print(f"   {worker_prefix} 2/3 Filling search input and submitting form...")
    try:
        search_input = page.locator("input[name='terms[0][value]'], input[id*='edit-terms-0']").first
        await search_input.wait_for(state="visible", timeout=10000)
        await search_input.click()
        await search_input.fill(search_term)

        submit_button = page.locator("#edit-submit, button.advanced-search-form__search").first
        
        async with page.expect_navigation(wait_until="networkidle", timeout=15000):
            if await submit_button.count() > 0:
                await submit_button.click(force=True)
            else:
                await search_input.press("Enter")

    except Exception:
        # Fallback for dynamic in-place Ajax view updates
        await search_input.press("Enter")
        await page.wait_for_timeout(2000)

    # 2. Extract Result Links & Result Count
    print(f"   {worker_prefix} 3/3 Extracting page count and row links...")
    
    try:
        search_data = await page.evaluate("""
            (baseUrl) => {
                // Helper to validate item links and filter out Drupal system/ajax endpoints
                const isValidItemUrl = (href) => {
                    if (!href) return false;
                    const lower = href.toLowerCase();
                    return (
                        !lower.startsWith('#') &&
                        !lower.startsWith('javascript:') &&
                        !lower.includes('/search') &&
                        !lower.includes('/views/ajax') &&
                        !lower.includes('/ajax')
                    );
                };

                // 1. Target Drupal's .pager__summary for total count
                let totalCount = 0;
                const pagerSummary = document.querySelector('.pager__summary, .view-header, .search-result-count');
                
                if (pagerSummary) {
                    const text = pagerSummary.innerText;
                    const match = text.match(/of\s+([\d,]+)/i) || text.match(/([\d,]+)\s+results/i);
                    if (match) {
                        totalCount = parseInt(match[1].replace(/,/g, ''), 10);
                    }
                }

                // 2. Extract item title links from each result row
                const itemLinks = [];
                const resultRows = document.querySelectorAll(
                    '.views-row, .search-result, article.node, .islandora-object'
                );

                resultRows.forEach(row => {
                    const anchor = row.querySelector('.views-field-title a, h2 a, h3 a, .field--name-title a, a');
                    if (anchor) {
                        const href = anchor.getAttribute('href');
                        if (isValidItemUrl(href)) {
                            const fullUrl = new URL(href, baseUrl).href;
                            itemLinks.push(fullUrl);
                        }
                    }
                });

                // Fallback: If no rows matched, collect content links inside main view container
                if (itemLinks.length === 0) {
                    const generalAnchors = document.querySelectorAll('.view-content a[href], main a[href]');
                    generalAnchors.forEach(a => {
                        const href = a.getAttribute('href');
                        if (isValidItemUrl(href)) {
                            itemLinks.push(new URL(href, baseUrl).href);
                        }
                    });
                }

                if (totalCount === 0) {
                    totalCount = itemLinks.length;
                }

                return {
                    resultCount: totalCount,
                    extractedLinks: itemLinks
                };
            }
        """, site_url)

        result_count = search_data.get("resultCount", 0)
        links = search_data.get("extractedLinks", [])

        return "Passed", result_count, links, "Search executed successfully via UI form interaction"

    except Exception as eval_err:
        return "Failed", 0, [], f"JS Evaluation Error: {str(eval_err).split('\n')[0]}"


async def worker(worker_id, queue, context, output_file_path):
    page = await context.new_page()

    while not queue.empty():
        idx, site_url, search_term = await queue.get()
        worker_prefix = f"[Worker {worker_id}] [{idx}]"
        print(f"{worker_prefix} Testing search for '{search_term}' on: {site_url}")

        js_errors = []
        page.on("pageerror", lambda exc: js_errors.append(str(exc).split("\n")[0]))

        status, count, links, details = await execute_search(page, site_url, search_term, worker_prefix)

        # Format array of links as a newline-separated string inside a single CSV cell
        formatted_links = "\n".join(links) if links else "None"

        if js_errors:
            details += f" | JS Errors ({len(js_errors)})"

        async with csv_write_lock:
            with open(output_file_path, "a", newline="", encoding="utf-8") as f_out:
                writer = csv.writer(f_out)
                writer.writerow([
                    site_url,
                    search_term,
                    status,
                    count,
                    formatted_links,
                    details
                ])

        print(f"{worker_prefix} Result: {status} | Count: {count} | Links Extracted: {len(links)}")
        await asyncio.sleep(random.uniform(1.0, 2.0))
        queue.task_done()

    await page.close()


async def worker(worker_id, queue, context, output_file_path):
    page = await context.new_page()

    while not queue.empty():
        idx, site_url, search_term = await queue.get()
        worker_prefix = f"[Worker {worker_id}] [{idx}]"
        print(f"{worker_prefix} Testing search for '{search_term}' on: {site_url}")

        js_errors = []

        page.on("pageerror", lambda exc: js_errors.append(str(exc).split("\n")[0]))

        status, count, links, details = await execute_search(page, site_url, search_term, worker_prefix)

        # Convert array of links to newline-separated string inside CSV cell
        formatted_links = "\n".join(links) if links else "None"

        if js_errors:
            details += f" | JS Errors ({len(js_errors)})"

        async with csv_write_lock:
            with open(output_file_path, "a", newline="", encoding="utf-8") as f_out:
                writer = csv.writer(f_out)
                writer.writerow([
                    site_url,
                    search_term,
                    status,
                    count,
                    formatted_links,
                    details
                ])

        print(f"{worker_prefix} Result: {status} | Count: {count} | Links Extracted: {len(links)}")
        await asyncio.sleep(random.uniform(1.0, 2.0))
        queue.task_done()

    await page.close()


async def run_search_tests():
    os.makedirs(settings.SEARCH_OUTPUT_DIR, exist_ok=True)

    input_file = getattr(settings, "SEARCH_INPUT_FILE", "data/search.csv")
    if not os.path.exists(input_file):
        print(f"❌ Error: {input_file} not found.")
        return

    tasks_list = []
    with open(input_file, "r", encoding="utf-8") as f_in:
        reader = csv.reader(f_in)
        next(reader, None)  # Skip header
        for row in reader:
            if len(row) >= 2:
                site_url = row[0].strip()
                term = row[1].strip()
                if site_url and term:
                    tasks_list.append((site_url, term))

    if not tasks_list:
        print("❌ No valid URL and Search Term pairs found in input file.")
        return

    output_file_path = get_dynamic_output_path()
    print(f"\n==========================================")
    print(f"🔍 WATCHER TEST SUITE - SEARCH MODULE")
    print(f"==========================================")
    print(f"Total Search Targets: {len(tasks_list)}")
    print(f"Output File: {output_file_path}\n")

    browser_mgr = BrowserManager()
    context = await browser_mgr.start()

    queue = asyncio.Queue()
    for idx, (url, term) in enumerate(tasks_list, 1):
        await queue.put((idx, url, term))

    headers = ["Site URL", "Search Term", "Test Status", "Total Results Count", "Extracted Links On Page", "Details"]
    with open(output_file_path, "w", newline="", encoding="utf-8") as f_out:
        writer = csv.writer(f_out)
        writer.writerow(headers)

    workers = [
        asyncio.create_task(worker(i, queue, context, output_file_path))
        for i in range(settings.CONCURRENT_WORKERS)
    ]

    await queue.join()

    for w in workers:
        w.cancel()

    await browser_mgr.stop()
    print(f"\n✅ Search testing complete. Saved to: {output_file_path}")


if __name__ == "__main__":
    asyncio.run(run_search_tests())