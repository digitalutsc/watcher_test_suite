# tests/test_viewers.py
import os
import sys
import csv
import random
import asyncio
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from src.browser import BrowserManager

csv_write_lock = asyncio.Lock()


def get_dynamic_output_path():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(settings.VIEWERS_OUTPUT_DIR, f"test_viewers_output_{timestamp}.csv")


# ---------------------------------------------------------------------------
# Individual Viewer Validators
# ---------------------------------------------------------------------------

async def validate_mirador(page, worker_prefix):
    """Validates Mirador initialization, IIIF manifest connection, and canvas tile rendering."""
    
    # 1. Check if Mirador wrapper container is attached to DOM
    print(f"   {worker_prefix} 1/3 Checking Mirador container wrapper...")
    mirador_container = page.locator("#mirador, .mirador-viewer, [id*='mirador'], .openseadragon-container").first
    try:
        await mirador_container.wait_for(state="attached", timeout=5000)
    except Exception:
        return False, "Mirador container wrapper (#mirador) not found in DOM"

    # 2. Wait for OpenSeadragon canvas layer to become visible
    print(f"   {worker_prefix} 2/3 Waiting for OpenSeadragon canvas layer...")
    canvas_locator = page.locator("canvas, .openseadragon-canvas").first
    try:
        await canvas_locator.wait_for(state="visible", timeout=10000)
    except Exception:
        return False, "Mirador wrapper found, but canvas layer failed to render within 10s"

    # 3. Check physical viewport dimensions and actual image tile presence
    print(f"   {worker_prefix} 3/3 Verifying canvas viewport dimensions and image tile render...")
    render_check = await page.evaluate("""
        () => {
            const canvases = document.querySelectorAll('canvas, .openseadragon-canvas');
            if (canvases.length === 0) return { success: false, reason: "No canvas elements found" };

            for (let c of canvases) {
                const rect = c.getBoundingClientRect();
                // Ensure canvas is rendered and visible on screen
                if (rect.width > 50 && rect.height > 50) {
                    return { 
                        success: true, 
                        width: Math.round(rect.width), 
                        height: Math.round(rect.height) 
                    };
                }
            }
            return { success: false, reason: "Canvas exists but has 0x0 or collapsed dimensions" };
        }
    """)

    if not render_check.get("success"):
        return False, f"Mirador rendering failed: {render_check.get('reason')}"

    return True, f"Mirador rendering verified ({render_check['width']}x{render_check['height']}px canvas active)"


async def validate_ableplayer(page, worker_prefix):
    """Validates AblePlayer container DOM presence, audio/video element attachment, and media stream loading state."""
    
    # 1. Check if AblePlayer container or native audio/video element is attached to DOM
    print(f"   {worker_prefix} 1/3 Checking AblePlayer container and media elements...")
    player_locator = page.locator(".able-player, video, audio, .able-wrapper").first
    try:
        await player_locator.wait_for(state="attached", timeout=5000)
    except Exception:
        return False, "AblePlayer container or <video>/<audio> tag not found in DOM"

    # 2. Check element visibility
    print(f"   {worker_prefix} 2/3 Checking if player interface is visible on screen...")
    if not await player_locator.is_visible(timeout=5000):
        return False, "AblePlayer container found in DOM, but element is hidden or collapsed (0x0)"

    # 3. Check HTML5 Media readyState and network state via browser JS
    print(f"   {worker_prefix} 3/3 Inspecting media stream load state (readyState)...")
    media_status = await page.evaluate("""
        () => {
            const media = document.querySelector('video, audio');
            if (!media) {
                return { loaded: false, reason: "No native <video> or <audio> element found inside player" };
            }

            const readyState = media.readyState;
            const networkState = media.networkState; // 3 = NETWORK_NO_SOURCE

            if (networkState === 3) {
                return { loaded: false, reason: "Media source error (networkState 3: NO_SOURCE / 404 asset)" };
            }

            if (readyState >= 1) { // Metadata loaded successfully
                return { 
                    loaded: true, 
                    src: media.currentSrc || media.src,
                    duration: media.duration,
                    readyState: readyState
                };
            }

            return { loaded: false, reason: `Media stuck loading (readyState: ${readyState})` };
        }
    """)

    if not media_status.get("loaded"):
        return False, f"AblePlayer visible, but media stream failed: {media_status.get('reason')}"

    return True, f"AblePlayer verified active (Stream: {media_status.get('readyState')} readyState, Duration: {round(media_status.get('duration', 0), 1)}s)"


async def validate_pdfjs(page, worker_prefix):
    """Validates Drupal/Islandora PDF.js iframe wrapper and inner canvas rendering."""
    
    # 1. Locate the PDF.js iframe in the Drupal media block
    print(f"   {worker_prefix} 1/3 Locating PDF.js iframe element...")
    iframe_locator = page.locator("iframe.pdf, iframe[src*='pdf.js'], iframe[src*='viewer.html']").first
    
    try:
        await iframe_locator.wait_for(state="attached", timeout=10000)
    except Exception:
        # Fallback check for non-iframe direct embeds
        iframe_locator = page.locator("#viewer, .pdfViewer, embed[type='application/pdf']").first
        try:
            await iframe_locator.wait_for(state="attached", timeout=5000)
        except Exception:
            return False, "PDF.js iframe/container not found in DOM"

    # 2. Get the Frame object inside the iframe
    print(f"   {worker_prefix} 2/3 Accessing iframe content frame & page rendering layer...")
    
    # Obtain frame handle (or fallback to page if top-level)
    frame_element = await iframe_locator.element_handle()
    target_frame = await frame_element.content_frame() if frame_element else None
    
    # If no content_frame (e.g. cross-origin restriction or not an iframe), default to main page
    if not target_frame:
        target_frame = page

    # Wait for PDF.js internal canvas or page container inside the iframe
    canvas_locator = target_frame.locator("canvas, .page, #viewer .page, .pdfViewer .page").first
    try:
        await canvas_locator.wait_for(state="visible", timeout=20000)
    except Exception:
        return False, "PDF iframe found, but internal canvas/page layer failed to render within 20s"

    # 3. Inspect canvas viewport dimensions inside the frame
    print(f"   {worker_prefix} 3/3 Verifying rendered PDF page dimensions...")
    render_check = await target_frame.evaluate("""
        () => {
            const elements = document.querySelectorAll('canvas, .page, embed');
            if (elements.length === 0) return { success: false, reason: "No canvas/page elements found inside iframe" };

            for (let el of elements) {
                const rect = el.getBoundingClientRect();
                if (rect.width > 50 && rect.height > 50) {
                    return { 
                        success: true, 
                        width: Math.round(rect.width), 
                        height: Math.round(rect.height) 
                    };
                }
            }
            return { success: false, reason: "PDF elements present inside iframe but have 0x0 dimensions" };
        }
    """)

    if not render_check.get("success"):
        return False, f"PDF.js rendering failed: {render_check.get('reason')}"

    return True, f"PDF.js rendering verified ({render_check['width']}x{render_check['height']}px active in iframe)"

# Dispatcher mapping normalized strings to functions
VIEWER_DISPATCHER = {
    "mirador": validate_mirador,
    "ableplayer": validate_ableplayer,
    "pdfjs": validate_pdfjs
}

# ---------------------------------------------------------------------------
# Worker & Orchestrator
# ---------------------------------------------------------------------------

async def worker(worker_id, queue, context, output_file_path):
    page = await context.new_page()

    while not queue.empty():
        idx, original_url, expected_viewer = await queue.get()
        worker_prefix = f"[Worker {worker_id}] [{idx}]"
        print(f"{worker_prefix} Testing ({expected_viewer}): {original_url}")

        js_errors = []
        network_failures = []

        # 1. Capture uncaught JavaScript errors with full message
        page.on("pageerror", lambda exc: js_errors.append(str(exc).split("\n")[0]))

        # 2. Capture failed network responses with HTTP Status Code and Target URL
        page.on(
            "response",
            lambda resp: network_failures.append(f"[{resp.status}] {resp.url}")
            if resp.status >= 400 and resp.request.resource_type in ["fetch", "xhr", "media", "document", "other", "script", "stylesheet"]
            else None
        )

        test_status = "Failed"
        details = ""

        try:
            await page.goto(original_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)  # Allow JS viewer initialization

            viewer_key = expected_viewer.strip().lower()

            if viewer_key in VIEWER_DISPATCHER:
                validator_func = VIEWER_DISPATCHER[viewer_key]
                passed, msg = await validator_func(page, worker_prefix)
                if passed:
                    test_status = "Passed"
                    details = msg
                else:
                    test_status = "Failed (Rendering)"
                    details = msg
            else:
                test_status = "Skipped"
                details = f"Skipping unsupported viewer: '{expected_viewer}'"

        except Exception as e:
            test_status = "Failed (Timeout/Error)"
            details = str(e).split("\n")[0]

        # Append exact JS errors and failed network request URLs to details
        if js_errors:
            details += f" | JS Errors: {'; '.join(js_errors)}"
        if network_failures:
            details += f" | Failed Assets: {'; '.join(network_failures)}"

        # Thread-safe writing
        async with csv_write_lock:
            with open(output_file_path, "a", newline="", encoding="utf-8") as f_out:
                writer = csv.writer(f_out)
                writer.writerow([
                    original_url,
                    expected_viewer,
                    test_status,
                    details,
                    "Yes" if js_errors else "No",
                    "Yes" if network_failures else "No"
                ])

        print(f"{worker_prefix} Result: {test_status} | {details}")
        await asyncio.sleep(random.uniform(1.0, 2.0))
        queue.task_done()

    await page.close()


async def run_viewer_tests():
    os.makedirs(settings.VIEWERS_OUTPUT_DIR, exist_ok=True)
    os.makedirs(settings.USER_DATA_DIR, exist_ok=True)

    if not os.path.exists(settings.VIEWERS_INPUT_FILE):
        print(f"❌ Error: {settings.VIEWERS_INPUT_FILE} not found.")
        return

    # Extract Column A (URL) and Column B (Viewer)
    tasks_list = []
    with open(settings.VIEWERS_INPUT_FILE, "r", encoding="utf-8") as f_in:
        reader = csv.reader(f_in)
        next(reader, None)  # Skip CSV header
        for row in reader:
            if len(row) >= 2:
                url = row[0].strip()
                viewer = row[1].strip()
                if url and viewer:
                    tasks_list.append((url, viewer))

    if not tasks_list:
        print("❌ No valid URL and Viewer pairs found in input file.")
        return

    output_file_path = get_dynamic_output_path()
    print(f"Total Viewer test cases: {len(tasks_list)}")
    print(f"Results writing to: {output_file_path}")

    browser_mgr = BrowserManager()
    context = await browser_mgr.start()

    queue = asyncio.Queue()
    for idx, (url, viewer) in enumerate(tasks_list, 1):
        await queue.put((idx, url, viewer))

    headers = ["URL", "Expected Viewer", "Test Status", "Details", "JS Errors", "Network Failures"]
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
    print(f"\n✅ Viewer QA testing complete. Output saved to {output_file_path}.")


if __name__ == "__main__":
    asyncio.run(run_viewer_tests())