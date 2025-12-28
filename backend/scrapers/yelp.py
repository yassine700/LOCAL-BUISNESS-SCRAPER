"""
Yelp scraper using JSON endpoints.
"""
import json
import re
from typing import List, Dict
from urllib.parse import quote
import logging

from backend.scrapers.base import BaseScraper
from backend.config import get_headers

logger = logging.getLogger(__name__)


class YelpScraper(BaseScraper):
    """Scraper for Yelp.com using JSON endpoints."""
    
    BASE_URL = "https://www.yelp.com"
    
    async def scrape(self, keyword: str, city: str) -> List[Dict[str, str]]:
        """
        Scrape Yelp for businesses.
        
        Args:
            keyword: Search keyword
            city: City name
            
        Returns:
            List of businesses with name and website
        """
        await self.delay()
        
        # Build search URL
        location = quote(f"{city}, US")
        search_term = quote(keyword)
        
        # Try the search endpoint
        url = f"{self.BASE_URL}/search/snippet?find_desc={search_term}&find_loc={location}&start=0&parent_request_id=abc123"
        
        logger.info(f"Scraping Yelp: {keyword} in {city}")
        
        # Use JSON-specific headers
        headers = get_headers()
        headers.update({
            "Accept": "application/json, text/plain, */*",
            "Referer": f"{self.BASE_URL}/search?find_desc={search_term}&find_loc={location}",
        })
        
        html = await self.fetch_page(url, headers=headers)
        if not html:
            logger.warning(f"Failed to fetch Yelp JSON for {city}, trying HTML fallback")
            return await self._scrape_html_fallback(keyword, city)
        
        return self._parse_json_results(html, keyword, city)
    
    def _parse_json_results(self, html: str, keyword: str, city: str) -> List[Dict[str, str]]:
        """Parse JSON response from Yelp."""
        businesses = []
        
        try:
            data = json.loads(html)
            
            # Navigate JSON structure (may vary)
            search_results = data.get("searchPageProps", {}).get("mainContentComponentsListProps", [])
            
            for component in search_results:
                if component.get("type") == "biz":  # Business result
                    biz_data = component.get("props", {}).get("business", {})
                    if biz_data:
                        name = biz_data.get("name", "")
                        website = biz_data.get("website", "") or biz_data.get("websiteUrl", "")
                        
                        if name:
                            businesses.append({
                                "business_name": name,
                                "website": website or ""
                            })
            
        except json.JSONDecodeError:
            # If not JSON, might be HTML
            logger.warning("Response was not JSON, trying HTML parsing")
            return self._parse_html_results(html, keyword, city)
        except Exception as e:
            logger.error(f"Error parsing Yelp JSON: {e}")
        
        if not businesses:
            # Fallback to HTML parsing
            return self._parse_html_results(html, keyword, city)
        
        logger.info(f"Found {len(businesses)} businesses on Yelp for {city}")
        return businesses
    
    async def _scrape_html_fallback(self, keyword: str, city: str) -> List[Dict[str, str]]:
        """Fallback to HTML scraping if JSON fails."""
        location = quote(f"{city}, US")
        search_term = quote(keyword)
        url = f"{self.BASE_URL}/search?find_desc={search_term}&find_loc={location}"
        
        html = await self.fetch_page(url)
        if not html:
            return []
        
        return self._parse_html_results(html, keyword, city)
    
    def _parse_html_results(self, html: str, keyword: str, city: str) -> List[Dict[str, str]]:
        """Parse HTML results from Yelp as fallback."""
        from bs4 import BeautifulSoup
        
        soup = BeautifulSoup(html, 'html.parser')
        businesses = []
        
        # Look for business listings
        listings = soup.find_all('div', class_=re.compile(r'business|listing|result', re.I))
        
        if not listings:
            # Try Yelp-specific structure
            listings = soup.find_all('div', {'data-testid': re.compile(r'business|result', re.I)})
        
        for listing in listings[:50]:  # Limit to 50
            try:
                # Extract business name
                name_elem = listing.find('a', class_=re.compile(r'business|name|link', re.I))
                if not name_elem:
                    name_elem = listing.find('h3') or listing.find('h2')
                
                business_name = name_elem.get_text(strip=True) if name_elem else None
                
                if not business_name:
                    continue
                
                # Extract website
                website = None
                website_elem = listing.find('a', href=re.compile(r'yelp.com/biz'))
                if website_elem:
                    # Yelp business URL, not the actual website
                    # We'll need to extract from business page or leave empty
                    pass
                
                # Look for website in text
                text = listing.get_text()
                url_pattern = re.compile(r'https?://[^\s<>"]+')
                urls = url_pattern.findall(text)
                if urls and 'yelp.com' not in urls[0]:
                    website = urls[0]
                
                businesses.append({
                    "business_name": business_name,
                    "website": website or ""
                })
                
            except Exception as e:
                logger.error(f"Error parsing Yelp listing: {e}")
                continue
        
        logger.info(f"Found {len(businesses)} businesses on Yelp (HTML) for {city}")
        return businesses

