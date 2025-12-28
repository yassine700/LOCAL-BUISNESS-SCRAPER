"""
Base scraper class with common anti-bot functionality.
"""
import asyncio
import random
from abc import ABC, abstractmethod
from typing import List, Dict, Optional
import httpx
from urllib.parse import quote
import logging

from backend.config import (
    REQUEST_TIMEOUT, MAX_RETRIES, RETRY_DELAY,
    MIN_DELAY, MAX_DELAY, PROXY_LIST, get_headers
)

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """Base class for all scrapers with anti-bot measures."""
    
    def __init__(self):
        self.proxy_list = [p.strip() for p in PROXY_LIST if p.strip()]
        self.proxy_index = 0
    
    def get_proxy(self) -> Optional[str]:
        """Get next proxy in rotation."""
        if not self.proxy_list:
            return None
        proxy = self.proxy_list[self.proxy_index % len(self.proxy_list)]
        self.proxy_index += 1
        return proxy
    
    async def delay(self):
        """Random delay between requests."""
        delay_time = random.uniform(MIN_DELAY, MAX_DELAY)
        await asyncio.sleep(delay_time)
    
    async def fetch_page(self, url: str, headers: Optional[dict] = None, 
                        max_retries: int = MAX_RETRIES) -> Optional[str]:
        """
        Fetch a page with retry logic and anti-bot measures.
        
        Args:
            url: URL to fetch
            headers: Optional custom headers
            max_retries: Maximum number of retries
            
        Returns:
            Page content as string or None if failed
        """
        if headers is None:
            headers = get_headers()
        
        proxy = self.get_proxy()
        
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(
                    timeout=REQUEST_TIMEOUT,
                    proxies=proxy if proxy else None,
                    follow_redirects=True
                ) as client:
                    response = await client.get(url, headers=headers)
                    
                    if response.status_code == 200:
                        return response.text
                    elif response.status_code == 403:
                        # Forbidden - likely bot detection
                        logger.warning(f"HTTP 403 Forbidden for {url}, attempt {attempt + 1}")
                        # Wait longer and try different approach
                        await asyncio.sleep(RETRY_DELAY * (attempt + 1) * 3)
                        # Could try different headers on retry
                    elif response.status_code == 429:
                        # Rate limited, wait longer
                        logger.warning(f"Rate limited for {url}, attempt {attempt + 1}")
                        await asyncio.sleep(RETRY_DELAY * (attempt + 1) * 2)
                    elif response.status_code >= 500:
                        # Server error, retry
                        logger.warning(f"Server error {response.status_code} for {url}, attempt {attempt + 1}")
                        await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                    else:
                        logger.error(f"HTTP {response.status_code} for {url}")
                        return None
                        
            except Exception as e:
                logger.error(f"Error fetching {url}: {e}, attempt {attempt + 1}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                else:
                    return None
        
        return None
    
    @abstractmethod
    async def scrape(self, keyword: str, city: str) -> List[Dict[str, str]]:
        """
        Scrape businesses for a keyword and city.
        
        Returns:
            List of dicts with keys: business_name, website
        """
        pass

