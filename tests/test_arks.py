# tests/test_arks.py
import os
import sys
import csv
import random
import asyncio
from datetime import datetime

# Forcefully append the parent directory (project root) to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from src.browser import BrowserManager

# Thread-safe lock for appending to the CSV file
csv_write_lock = asyncio.Lock()

def get_dynamic_output_path():
    """
    Generates an output path based on the input filename and current timestamp,
    targeted directly to the configured output directory.
    Example: 'data/arks.csv' -> 'outputs/arks_20260716_132000.csv'
    """
    input_filename = os.path.basename(settings.INPUT_FILE)
    name_part, ext_part = os.path.splitext(input_filename)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"{name_part}_{timestamp}{ext_part}"
    
    return os.path.join(settings.OUTPUT_DIR, output_filename)

def extract_ark_identifier(url):
    """
    Extracts the core archival identifier string from the ARK URL.
    """
    if "ark:" in url:
        return url.split("ark:")[-1].strip()
    return None

async def determine_page_status(page, final_url):
    """Evaluates the page status using the final landing URL and the page DOM."""
    if "404.php" in final_url:
        return "Failed (404 Page Not Found - Redirected to 404.php)"

    try:
        body_text = await page.locator("body").text_content() or ""
        if "BotStopper" in body_text or "Techaro" in body_text:
            return "Failed (Blocked by BotStopper)"
    except Exception:
        pass

    try:
        title_element = page.locator(".block-page-title-block h1.title span").first
        if await title_element.is_visible(timeout=2000):
            title_text = (await title_element.text_content() or "").strip()
            if "403 Access Denied" in title_text:
                return "Failed (403 Access Denied)"
            elif "404 Page Not Found" in title_text:
                return "Failed (404 Page Not Found)"
    except Exception:
        pass

    return "Success"

async def block_unnecessary_resources(route):
    """Aborts requests for images, fonts, and stylesheets to maximize speed."""
    if route.request.resource_type in ["image", "font", "media", "stylesheet"]:
        await route.abort()
    else:
        await route.continue_()

async def worker(worker_id, queue, context, output_file_path):
    """A worker that grabs URLs from the queue and processes them concurrently."""
    page = await context.new_page()
    await page.route("**/*", block_unnecessary_resources)

    while not queue.empty():
        idx, original_url = await queue.get()
        print(f"[Worker {worker_id}] [{idx}] Processing: {original_url}")
        
        final_url = "N/A"
        status_desc = "Pending"
        ark_identifier = extract_ark_identifier(original_url) or "N/A"
        ark_match_status = "N/A"

        try:
            await page.goto(original_url, wait_until="commit", timeout=30000)
            await page.wait_for_timeout(1000) 
            
            final_url = page.url
            status_desc = await determine_page_status(page, final_url)

            # Match check
            if status_desc == "Success" and ark_identifier != "N/A":
                if ark_identifier in final_url:
                    ark_match_status = "Match"
                else:
                    ark_match_status = "Mismatch"

        except Exception as e:
            status_desc = f"Error: {str(e)}"

        # Thread-safe write to CSV
        async with csv_write_lock:
            with open(output_file_path, "a", newline="", encoding="utf-8") as f_out:
                writer = csv.writer(f_out)
                writer.writerow([
                    original_url, 
                    final_url, 
                    status_desc, 
                    ark_identifier, 
                    ark_match_status
                ])

        print(f"[Worker {worker_id}] [{idx}] Finished: {status_desc} | Match: {ark_match_status}")
        await asyncio.sleep(random.uniform(1.0, 2.5))
        queue.task_done()

    await page.close()

async def run_ark_tests():
    # Ensure all directories exist before processing
    os.makedirs(settings.OUTPUT_DIR, exist_ok=True)  # <--- Creates outputs/ folder
    os.makedirs(settings.USER_DATA_DIR, exist_ok=True)

    if not os.path.exists(settings.INPUT_FILE):
        print(f"Error: {settings.INPUT_FILE} not found.")
        return

    # Extract Column A
    urls = []
    with open(settings.INPUT_FILE, "r", encoding="utf-8") as f_in:
        reader = csv.reader(f_in)
        next(reader, None)  # Skip the first row (header row)
        for row in reader:
            if row:
                first_cell = row[0].strip()
                if first_cell:
                    urls.append(first_cell)

    if not urls:
        print("No valid URLs found in Column A.")
        return

    # Dynamically generate the output filepath in outputs/
    output_file_path = get_dynamic_output_path()
    print(f"Total URLs to test: {len(urls)}")
    print(f"Results will write dynamically to: {output_file_path}")
    
    CONCURRENT_WORKERS = settings.CONCURRENT_WORKERS
    print(f"Launching {CONCURRENT_WORKERS} parallel workers...\n")

    browser_mgr = BrowserManager()
    context = await browser_mgr.start()

    # Create & populate queue
    queue = asyncio.Queue()
    for idx, url in enumerate(urls, 1):
        await queue.put((idx, url))

    # Initialize dynamic output CSV with headers
    headers = ["Original URL", "Final URL", "Status", "ARK Identifier", "ARK Match"]
    with open(output_file_path, "w", newline="", encoding="utf-8") as f_out:
        writer = csv.writer(f_out)
        writer.writerow(headers)

    # Start workers concurrently
    workers = [asyncio.create_task(worker(i, queue, context, output_file_path)) for i in range(CONCURRENT_WORKERS)]

    # Wait until all URLs are processed
    await queue.join()

    # Terminate remaining idle workers
    for w in workers:
        w.cancel()

    await browser_mgr.stop()
    print(f"\nAll tasks complete. Output saved to {output_file_path}.")