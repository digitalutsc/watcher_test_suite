# tests/test_robots.py
import os
import sys
import csv
import robots  # Uses robotspy
from datetime import datetime

# Forcefully append the parent directory (project root) to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings

def get_dynamic_output_path():
    """Generates an output path inside outputs/ for the robots results."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(settings.OUTPUT_DIR, f"test_robots_output_{timestamp}.csv")

def run_robots_tests():
    print("\n==========================================")
    print("🤖 Running Robots.txt Validation Suite")
    print("==========================================")

    # 1. Verify files exist
    if not os.path.exists(settings.LOCAL_ROBOTS_PATH):
        print(f"❌ Error: Could not find '{settings.LOCAL_ROBOTS_PATH}'")
        return
    if not os.path.exists(settings.ROBOTS_URLS_FILE):
        print(f"❌ Error: Could not find '{settings.ROBOTS_URLS_FILE}'")
        return

    os.makedirs(settings.OUTPUT_DIR, exist_ok=True)
    output_file_path = get_dynamic_output_path()

    # 2. Read the local robots.txt content
    print(f"Reading local configuration from: {settings.LOCAL_ROBOTS_PATH}")
    with open(settings.LOCAL_ROBOTS_PATH, "r", encoding="utf-8") as f:
        robots_content = f.read()

    # 3. Initialize the parser
    parser = robots.RobotsParser.from_string(robots_content)

    # 4. Read the URLs to test
    print(f"Reading target URLs from: {settings.ROBOTS_URLS_FILE}")
    with open(settings.ROBOTS_URLS_FILE, "r", encoding="utf-8") as f:
        urls_to_test = [line.strip() for line in f if line.strip()]

    if not urls_to_test:
        print("❌ No URLs found in file to test.")
        return

    print(f"Processing {len(urls_to_test)} URLs against User-Agent: '{settings.ROBOTS_USER_AGENT}'...")

    # Initialize output CSV file with headers
    headers = ["Tested URL", "User-Agent Checked", "Crawling Allowed"]
    with open(output_file_path, "w", newline="", encoding="utf-8") as f_out:
        writer = csv.writer(f_out)
        writer.writerow(headers)

    allowed_count = 0
    disallowed_count = 0

    # 5. Run the rules parser and write instantly
    for idx, url in enumerate(urls_to_test, 1):
        is_allowed = parser.can_fetch(settings.ROBOTS_USER_AGENT, url)
        
        if is_allowed:
            status_text = "Allowed"
            allowed_count += 1
            print(f"[{idx}/{len(urls_to_test)}] ✅ ALLOWED: {url}")
        else:
            status_text = "Disallowed"
            disallowed_count += 1
            print(f"[{idx}/{len(urls_to_test)}] ❌ DISALLOWED: {url}")

        # Append row immediately
        with open(output_file_path, "a", newline="", encoding="utf-8") as f_out:
            writer = csv.writer(f_out)
            writer.writerow([url, settings.ROBOTS_USER_AGENT, status_text])

    # Summary Output
    print("\n--- Summary ---")
    print(f"Total URLs processed: {len(urls_to_test)}")
    print(f"Allowed: {allowed_count} | Disallowed: {disallowed_count}")
    print(f"Results successfully logged to: {output_file_path}\n")