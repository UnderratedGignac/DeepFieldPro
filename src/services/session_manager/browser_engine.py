"""
Browser Engine for Session Management

Handles browser automation for odds acquisition from various sportsbooks.
Manages browser instances, sessions, and headless browsing operations.
"""

import asyncio
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright, Browser, BrowserContext, Page


class BrowserEngine:
    """
    Manages browser instances for web scraping and session handling.
    
    Provides capabilities for:
    - Creating and managing browser instances
    - Handling multiple browser contexts for parallel sessions
    - Managing cookies and session state
    - Stealth browsing to avoid detection
    """
    
    def __init__(self, headless: bool = True, user_data_dir: Optional[str] = None):
        self.headless = headless
        self.user_data_dir = user_data_dir
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._contexts: Dict[str, BrowserContext] = {}
        
    async def start(self) -> None:
        """Initialize the Playwright instance and launch browser."""
        self._playwright = await async_playwright().start()
        
        browser_args = [
            '--disable-blink-features=AutomationControlled',
            '--no-sandbox',
            '--disable-dev-shm-usage',
        ]
        
        if self.user_data_dir:
            browser_args.append(f'--user-data-dir={self.user_data_dir}')
            
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=browser_args
        )
        
    async def stop(self) -> None:
        """Close browser and cleanup resources."""
        # Close all contexts
        for context in self._contexts.values():
            await context.close()
        self._contexts.clear()
        
        if self._browser:
            await self._browser.close()
            self._browser = None
            
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
            
    async def create_context(self, context_id: str, proxy: Optional[Dict[str, str]] = None) -> BrowserContext:
        """
        Create a new browser context for isolated session.
        
        Args:
            context_id: Unique identifier for this context
            proxy: Optional proxy configuration
            
        Returns:
            BrowserContext instance
        """
        if not self._browser:
            raise RuntimeError("Browser not started. Call start() first.")
            
        context_options = {
            'viewport': {'width': 1920, 'height': 1080},
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
        
        if proxy:
            context_options['proxy'] = proxy
            
        context = await self._browser.new_context(**context_options)
        self._contexts[context_id] = context
        
        # Inject stealth scripts
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
        
        return context
        
    async def get_context(self, context_id: str) -> Optional[BrowserContext]:
        """Retrieve an existing context by ID."""
        return self._contexts.get(context_id)
        
    async def remove_context(self, context_id: str) -> None:
        """Close and remove a context."""
        if context_id in self._contexts:
            await self._contexts[context_id].close()
            del self._contexts[context_id]
            
    async def new_page(self, context_id: str) -> Page:
        """Create a new page within a context."""
        context = await self.get_context(context_id)
        if not context:
            raise ValueError(f"Context {context_id} does not exist")
        return await context.new_page()
        
    async def save_cookies(self, context_id: str, filepath: str) -> None:
        """Save cookies from a context to a file."""
        context = await self.get_context(context_id)
        if context:
            cookies = await context.cookies()
            import json
            with open(filepath, 'w') as f:
                json.dump(cookies, f)
                
    async def load_cookies(self, context_id: str, filepath: str) -> None:
        """Load cookies from a file into a context."""
        import json
        context = await self.get_context(context_id)
        if context:
            with open(filepath, 'r') as f:
                cookies = json.load(f)
            await context.add_cookies(cookies)
