# src/browser.py
from playwright.async_api import async_playwright
from config import settings

class BrowserManager:
    def __init__(self):
        self.playwright = None
        self.context = None

    async def start(self):
        self.playwright = await async_playwright().start()
        
        # Build standard args without forced headless overrides
        chrome_args = [
            "--disable-blink-features=AutomationControlled"
        ]

        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=settings.USER_DATA_DIR,
            headless=settings.HEADLESS, # Reads False from config.json
            channel="chrome",
            viewport=settings.VIEWPORT,
            user_agent=settings.USER_AGENT,
            args=chrome_args
        )
        return self.context

    async def stop(self):
        if self.context:
            await self.context.close()
        if self.playwright:
            await self.playwright.stop()