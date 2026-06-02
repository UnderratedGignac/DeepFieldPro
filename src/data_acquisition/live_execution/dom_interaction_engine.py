# dom_interaction_engine.py
import asyncio
import logging
from playwright.async_api import Page, Locator, Error as PlaywrightError

logger = logging.getLogger(__name__)

class DomInteractionEngine:
    """
    Retry-safe wrappers around Playwright actions to protect against Asynchronous DOM Race Conditions.
    Handles suspensions, odds changes, and React rerenders safely.
    """
    def __init__(self):
        self.MAX_RETRIES = 3
        self.RETRY_DELAY_MS = 100

    async def safe_click(self, page: Page, selector: str, timeout: int = 2000) -> bool:
        """
        Attempts to click an element, verifying visibility and retrying if the DOM invalidates.
        Returns True if successful, False if market suspended or timeout.
        """
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                locator = page.locator(selector).first
                
                # State Synchronization
                await locator.wait_for(state="visible", timeout=timeout)
                await locator.wait_for(state="attached", timeout=timeout)
                
                # Check for market suspension overlays
                suspension_overlay = page.locator("data-test-id='market-suspended-overlay'")
                if await suspension_overlay.is_visible():
                    logger.warning(f"[DOM ENGINE] Market suspended overlay detected before clicking {selector}")
                    return False
                    
                await locator.click(timeout=timeout)
                return True
                
            except PlaywrightError as e:
                logger.warning(f"[DOM ENGINE] Click attempt {attempt} failed for {selector}: {str(e)}")
                if attempt == self.MAX_RETRIES:
                    logger.error(f"[DOM ENGINE] Exhausted retries for {selector}")
                    return False
                await asyncio.sleep(self.RETRY_DELAY_MS / 1000.0)
                
        return False

    async def safe_fill(self, page: Page, selector: str, value: str, timeout: int = 1500) -> bool:
        """
        Retry-safe input filling.
        """
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                locator = page.locator(selector).first
                await locator.wait_for(state="visible", timeout=timeout)
                await locator.fill(value, timeout=timeout)
                return True
            except PlaywrightError as e:
                logger.warning(f"[DOM ENGINE] Fill attempt {attempt} failed for {selector}: {str(e)}")
                if attempt == self.MAX_RETRIES:
                    return False
                await asyncio.sleep(self.RETRY_DELAY_MS / 1000.0)
                
        return False

dom_engine = DomInteractionEngine()
