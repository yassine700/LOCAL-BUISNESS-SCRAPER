"""
Generic Proxy API client for residential proxy and request execution.

Supports any proxy service (ScrapingBee, Bright Data, Apify, etc).
The actual provider is determined by the API key format and endpoint configuration.
"""
import os
import asyncio
import logging
from typing import Optional
import httpx

logger = logging.getLogger(__name__)


class ProxyAPIClient:
    """
    Generic Proxy API client for high-volume YellowPages scraping.
    Works with any proxy service provider that accepts API keys.
    
    Supports:
    - ScrapingBee (https://www.scrapingbee.com/)
    - Bright Data (https://brightdata.com/)
    - Apify (https://apify.com/)
    - Any similar proxy service
    """
    
    # ScrapingBee endpoint (can be changed to other providers)
    BASE_URL = "https://app.scrapingbee.com/api/v1/"
    
    def __init__(self):
        self.api_key = os.getenv("PROXY_API_KEY")
        if not self.api_key:
            raise ValueError(
                "PROXY_API_KEY environment variable is required. "
                "Supports: ScrapingBee, Bright Data, Apify, or any similar proxy service."
            )
        # Never log or print the API key
        self._validate_api_key()
    
    def _validate_api_key(self):
        """Validate API key format (basic check without exposing it)."""
        if len(self.api_key) < 10:
            raise ValueError("Invalid PROXY_API_KEY format")
    
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
        Fetch URL through Proxy API (ScrapingBee, Bright Data, Apify, etc).
        
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
                            logger.error("Proxy API: Invalid API key")
                        else:
                            logger.error(f"Proxy API: {error_msg}")
                        return None
                    elif response.status_code == 429:
                        # Rate limited
                        logger.warning(f"Proxy API rate limited (attempt {attempt + 1}/{retries})")
                        if attempt < retries - 1:
                            await asyncio.sleep(delay_before_retry * (attempt + 1))
                        else:
                            return None
                    elif response.status_code >= 500:
                        # Server error - retry
                        logger.warning(f"Proxy API server error {response.status_code} (attempt {attempt + 1}/{retries})")
                        if attempt < retries - 1:
                            await asyncio.sleep(delay_before_retry * (attempt + 1))
                        else:
                            return None
                    else:
                        logger.error(f"ScrapingBee HTTP {response.status_code} for {url}")
                        return None
                        
            except httpx.TimeoutException:
                logger.warning(f"Proxy API timeout (attempt {attempt + 1}/{retries})")
                if attempt < retries - 1:
                    await asyncio.sleep(delay_before_retry * (attempt + 1))
                else:
                    return None
            except Exception as e:
                logger.error(f"Proxy API error: {e} (attempt {attempt + 1}/{retries})")
                if attempt < retries - 1:
                    await asyncio.sleep(delay_before_retry * (attempt + 1))
                else:
                    return None
        
        return None


# Backward compatibility alias
ScrapingBeeClient = ProxyAPIClient

# Global client instance (lazy initialization)
_proxy_api_client: Optional[ProxyAPIClient] = None


def get_scrapingbee_client() -> ProxyAPIClient:
    """Get or create proxy API client instance."""
    global _proxy_api_client
    if _proxy_api_client is None:
        _proxy_api_client = ProxyAPIClient()
    return _proxy_api_client

