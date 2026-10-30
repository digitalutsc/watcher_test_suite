# config/settings.py
import os
import yaml
from dotenv import load_dotenv

# Load variables from .env file in the root directory
load_dotenv()

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yml")

def load_config():
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(f"Configuration file not found at: {CONFIG_PATH}")
        
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

_config = load_config()

# Browser settings
BROWSER_SETTINGS = _config.get("browser_settings", {})
HEADLESS = BROWSER_SETTINGS.get("headless", True)
VIEWPORT = {
    "width": BROWSER_SETTINGS.get("viewport_width", 1280),
    "height": BROWSER_SETTINGS.get("viewport_height", 800)
}
USER_AGENT = BROWSER_SETTINGS.get("user_agent", "")
CONCURRENT_WORKERS = BROWSER_SETTINGS.get("concurrent_workers", 1)

# Suite configs
TEST_TO_RUN = _config.get("test_to_run", ["test_viewers"])

TEST_VIEWERS_CONFIG = _config.get("test_viewers", {})
VIEWERS_INPUT_FILE = TEST_VIEWERS_CONFIG.get("input_file", "data/viewers.csv")
VIEWERS_OUTPUT_DIR = TEST_VIEWERS_CONFIG.get("output_dir", "output")

USER_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tmp", "user_data")

# --- Performance Suite Configs ---
TEST_PERF_CONFIG = _config.get("test_performance", {})
PERF_INPUT_FILE = TEST_PERF_CONFIG.get("input_file", "data/urls_performance.csv")
PERF_OUTPUT_DIR = TEST_PERF_CONFIG.get("output_dir", "output")
PERF_STRATEGY = TEST_PERF_CONFIG.get("strategy", "desktop")

# 🔑 Read API Key exclusively from environment / .env file
PERF_API_KEY = os.getenv("PAGESPEED_API_KEY", "")

# --- Search Suite Configs ---
TEST_SEARCH_CONFIG = _config.get("test_search", {})
SEARCH_INPUT_FILE = TEST_SEARCH_CONFIG.get("input_file", "data/search.csv")
SEARCH_OUTPUT_DIR = TEST_SEARCH_CONFIG.get("output_dir", "output")

# --- SEO Configs ---
TEST_ROBOTS_CONFIG = _config.get("test_robots", {})
LOCAL_ROBOTS_PATH = TEST_ROBOTS_CONFIG.get("local_robots_path", "data/robots.txt")
ROBOTS_URLS_FILE = TEST_ROBOTS_CONFIG.get("input_file", "data/urls.txt")
ROBOTS_USER_AGENT = TEST_ROBOTS_CONFIG.get("user_agent", "Googlebot")
OUTPUT_DIR = TEST_ROBOTS_CONFIG.get("output_dir", "output")