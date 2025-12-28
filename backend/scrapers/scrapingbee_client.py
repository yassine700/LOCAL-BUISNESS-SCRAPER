"""
ScrapingBee API client for residential proxy and request execution.
"""
import os
import asyncio
import logging
from typing import Optional
import httpx

logger = logging.getLogger(__name__)


class ScrapingBeeClient:
    """
    ScrapingBee API client for high-volume YellowPages scraping.
    Handles residential proxies, browser emulation, and anti-bot measures.
    """
    
    BASE_URL = "https://app.scrapingbee.com/api/v1/"
    
    def __init__(self):
        self.api_key = os.getenv("SCRAPINGBEE_API_KEY")
        if not self.api_key:
            raise ValueError(
                "SCRAPINGBEE_API_KEY environment variable is required. "
                "Get your API key from https://www.scrapingbee.com/"
            )
        # Never log or print the API key
        self._validate_api_key()
    
    def _validate_api_key(self):
        """Validate API key format (basic check without exposing it)."""
        if len(self.api_key) < 10:
            raise ValueError("Invalid SCRAPINGBEE_API_KEY format")
    
    async def fetch_url(
        self,
        url: str,
        render_js: bool = False,
        country_code: str = "us",
        premium_proxy: bool = True,
        timeout: int = 30000,
        retries: int = 3,
        delay_before_retry: float = 2.0
    ) -> Optional[str]:
        """
        Fetch URL through ScrapingBee API.
        
        Args:
            url: Target URL to scrape
            render_js: Whether to render JavaScript (False for YellowPages)
            country_code: Country code for residential proxy (default: "us")
            premium_proxy: Use premium residential proxies (default: True)
            timeout: Request timeout in milliseconds (default: 30000 = 30s)
            retries: Number of retry attempts on failure
            delay_before_retry: Seconds to wait before retry
            
        Returns:
            HTML content as string, or None if failed
        """
        params = {
            "api_key": self.api_key,  # API key in params (ScrapingBee requirement)
            "url": url,
            "render_js": "true" if render_js else "false",
            "country_code": country_code,
            "premium_proxy": "true" if premium_proxy else "false",
            "block_resources": "false",
            "timeout": str(timeout),
        }
        
        for attempt in range(retries):
            try:
                async with httpx.AsyncClient(timeout=timeout / 1000 + 10) as client:
                    response = await client.get(self.BASE_URL, params=params)
                    
                    if response.status_code == 200:
                        return response.text
                    elif response.status_code == 400:
                        # Bad request - check response for details (don't log API key)
                        error_msg = response.text[:200] if response.text else "Bad request"
                        if "api_key" in error_msg.lower():
                            logger.error("ScrapingBee: Invalid API key")
                        else:
                            logger.error(f"ScrapingBee: {error_msg}")
                        return None
                    elif response.status_code == 429:
                        # Rate limited
                        logger.warning(f"ScrapingBee rate limited (attempt {attempt + 1}/{retries})")
                        if attempt < retries - 1:
                            await asyncio.sleep(delay_before_retry * (attempt + 1))
                        else:
                            return None
                    elif response.status_code >= 500:
                        # Server error - retry
                        logger.warning(f"ScrapingBee server error {response.status_code} (attempt {attempt + 1}/{retries})")
                        if attempt < retries - 1:
                            await asyncio.sleep(delay_before_retry * (attempt + 1))
                        else:
                            return None
                    else:
                        logger.error(f"ScrapingBee HTTP {response.status_code} for {url}")
                        return None
                        
            except httpx.TimeoutException:
                logger.warning(f"ScrapingBee timeout (attempt {attempt + 1}/{retries})")
                if attempt < retries - 1:
                    await asyncio.sleep(delay_before_retry * (attempt + 1))
                else:
                    return None
            except Exception as e:
                logger.error(f"ScrapingBee error: {e} (attempt {attempt + 1}/{retries})")
                if attempt < retries - 1:
                    await asyncio.sleep(delay_before_retry * (attempt + 1))
                else:
                    return None
        
        return None


# Global client instance (lazy initialization)
_scrapingbee_client: Optional[ScrapingBeeClient] = None


def get_scrapingbee_client() -> ScrapingBeeClient:
    """Get or create ScrapingBee client instance."""
    global _scrapingbee_client
    if _scrapingbee_client is None:
        _scrapingbee_client = ScrapingBeeClient()
    return _scrapingbee_client

