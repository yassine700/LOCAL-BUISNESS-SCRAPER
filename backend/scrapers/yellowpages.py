"""
YellowPages scraper with pagination and detail page crawling.
Uses ScrapingBee for residential proxy and anti-bot protection.
"""
import re
import random
import asyncio
from typing import List, Dict, Optional
from urllib.parse import quote, urljoin
from bs4 import BeautifulSoup
import logging

from backend.scrapers.base import BaseScraper
from backend.config import get_headers, USE_SCRAPINGBEE, MAX_PAGES
from backend.scrapers.scrapingbee_client import get_scrapingbee_client

logger = logging.getLogger(__name__)

# State abbreviation map
STATE_MAP = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID",
    "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS",
    "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
    "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC",
    "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT",
    "Vermont": "VT", "Virginia": "VA", "Washington": "WA", "West Virginia": "WV",
    "Wisconsin": "WI", "Wyoming": "WY", "District of Columbia": "DC",
    # Common variations
    "Ohio": "OH", "Florida": "FL", "Texas": "TX", "California": "CA",
    "New York": "NY", "Pennsylvania": "PA", "Illinois": "IL", "Michigan": "MI",
}


def normalize_location(city: str) -> str:
    """
    Normalize city location to format: "City, ST"
    Examples:
        "Toledo, Ohio" → "Toledo, OH"
        "St. Petersburg, FL" → "St Petersburg, FL"
        "Laredo, TX" → "Laredo, TX"
    """
    # Remove extra whitespace
    city = city.strip()
    
    # Split by comma
    parts = [p.strip() for p in city.split(",")]
    
    if len(parts) < 2:
        # No state provided, return as-is (might cause issues but better than crashing)
        logger.warning(f"City format unclear: {city}, using as-is")
        return city.replace(".", "").strip()
    
    # Clean city name (remove periods, extra spaces)
    city_name = parts[0].replace(".", "").strip()
    
    # Get state and normalize
    state = parts[1].strip()
    
    # Handle state abbreviations (already abbreviated)
    if len(state) == 2 and state.isupper():
        state = state.upper()
    else:
        # Try to map full state name to abbreviation
        state = STATE_MAP.get(state, state)
        # If still not found, try title case
        if state not in STATE_MAP.values():
            state = STATE_MAP.get(state.title(), state[:2].upper() if len(state) >= 2 else state)
    
    return f"{city_name}, {state}"


class YellowPagesScraper(BaseScraper):
    """Scraper for YellowPages.com with pagination and detail page crawling."""
    
    BASE_URL = "https://www.yellowpages.com"
    
    async def scrape(self, keyword: str, city: str, job_id: Optional[str] = None, 
                    on_business_scraped=None) -> List[Dict[str, str]]:
        """
        Scrape YellowPages for businesses with pagination and detail pages.
        
        Args:
            keyword: Search keyword
            city: City name (will be normalized)
            job_id: Optional job ID for progress tracking and resume capability
            on_business_scraped: Optional callback(business, is_duplicate, page, city)
            
        Returns:
            List of businesses with name and website
        """
        # Normalize location format
        normalized_city = normalize_location(city)
        logger.info(f"Scraping YellowPages: '{keyword}' in '{normalized_city}' (normalized from '{city}')")
        
        # Resume from last page if job_id provided
        start_page = 1
        if job_id:
            from backend.database import db
            start_page = db.get_scrape_progress(job_id, keyword, normalized_city)
            if start_page > 0:
                logger.info(f"Resuming from page {start_page + 1} for {normalized_city}")
                start_page += 1  # Start from next page
        
        all_businesses = []
        
        # Step 1: Scrape all pages with listings
        for page in range(start_page, MAX_PAGES + 1):
            # Check job status before each page
            if job_id:
                from backend.database import db
                status = db.get_job_status_simple(job_id)
                
                if status == "killed":
                    logger.info(f"Job {job_id} was killed, stopping scraping")
                    break
                elif status == "paused":
                    # Wait in a loop until resumed or killed
                    logger.info(f"Job {job_id} is paused, waiting...")
                    while True:
                        await asyncio.sleep(2)  # Check every 2 seconds
                        status = db.get_job_status_simple(job_id)
                        if status == "killed":
                            logger.info(f"Job {job_id} was killed while paused")
                            return all_businesses
                        elif status == "running":
                            logger.info(f"Job {job_id} resumed, continuing...")
                            break
                        elif status in ["completed", "error"]:
                            return all_businesses
            
            await self.delay()  # Human-like delay between pages
            
            # Build URL with pagination
            url = self._build_search_url(keyword, normalized_city, page)
            
            logger.info(f"Fetching page {page} for {normalized_city}")
            
            # Get listing page
            html = await self._fetch_listing_page(url)
            if not html:
                logger.warning(f"Failed to fetch page {page} for {normalized_city}")
                break
            
            # Parse listings from this page
            listings = self._parse_listing_page(html)
            
            if not listings:
                logger.info(f"No listings found on page {page}, stopping pagination")
                break
            
            logger.info(f"Found {len(listings)} listings on page {page}")
            
            # Step 2: For each listing, visit detail page to get website
            for listing in listings:
                # Check job status before each detail page
                if job_id:
                    from backend.database import db
                    status = db.get_job_status_simple(job_id)
                    if status == "killed":
                        logger.info(f"Job {job_id} was killed, stopping scraping")
                        return all_businesses
                    elif status == "paused":
                        # Enter pause loop
                        while True:
                            await asyncio.sleep(2)
                            status = db.get_job_status_simple(job_id)
                            if status == "killed":
                                return all_businesses
                            elif status == "running":
                                break
                            elif status in ["completed", "error"]:
                                return all_businesses
                
                await self.delay()  # Human-like delay between detail pages
                
                business_data = await self._scrape_detail_page(listing)
                if business_data:
                    all_businesses.append(business_data)
                    # Call callback if provided (for real-time updates)
                    if on_business_scraped:
                        on_business_scraped(business_data, False, page, normalized_city)
            
            # Save progress after each page
            if job_id:
                from backend.database import db
                db.save_scrape_progress(job_id, keyword, normalized_city, page)
            
            # If we got fewer listings than expected, might be last page
            if len(listings) < 30:  # YellowPages typically shows 30 per page
                logger.info(f"Few listings on page {page}, likely last page")
                break
        
        logger.info(f"Total businesses scraped for {normalized_city}: {len(all_businesses)}")
        return all_businesses
    
    def _build_search_url(self, keyword: str, city: str, page: int = 1) -> str:
        """Build YellowPages search URL with pagination."""
        search_terms = quote(keyword)
        geo_location = quote(city)
        
        if page == 1:
            url = f"{self.BASE_URL}/search?search_terms={search_terms}&geo_location_terms={geo_location}"
        else:
            url = f"{self.BASE_URL}/search?search_terms={search_terms}&geo_location_terms={geo_location}&page={page}"
        
        return url
    
    async def _fetch_listing_page(self, url: str) -> Optional[str]:
        """
        Fetch a listing page using ScrapingBee (if enabled) or direct HTTP.
        """
        if USE_SCRAPINGBEE:
            # Use ScrapingBee for residential proxy and anti-bot protection
            try:
                client = get_scrapingbee_client()
                html = await client.fetch_url(
                    url=url,
                    render_js=False,  # YellowPages doesn't require JS
                    country_code="us",
                    premium_proxy=True,
                    timeout=30000,
                    retries=3
                )
                return html
            except Exception as e:
                logger.error(f"ScrapingBee error: {e}")
                # Fallback to direct HTTP if ScrapingBee fails
                logger.info("Falling back to direct HTTP request")
        
        # Fallback: Direct HTTP request (for local testing without ScrapingBee)
        headers = get_headers()
        headers.update({
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.google.com/" if random.random() > 0.5 else self.BASE_URL,
            "Upgrade-Insecure-Requests": "1",
        })
        
        return await self.fetch_page(url, headers=headers)
    
    def _parse_listing_page(self, html: str) -> List[Dict[str, str]]:
        """
        Parse listing page to extract business names and profile URLs.
        Returns list of dicts with 'name' and 'profile_url'.
        """
        soup = BeautifulSoup(html, 'html.parser')
        listings = []
        
        # Try various selectors for YellowPages listings
        # Common YellowPages structures:
        # - div with class containing "result"
        # - article tags
        # - div with data-testid
        
        listing_elements = (
            soup.find_all('div', class_=re.compile(r'result|srp-listing|organic', re.I)) or
            soup.find_all('article') or
            soup.find_all('div', {'data-testid': re.compile(r'listing|result', re.I)}) or
            soup.find_all('div', class_=re.compile(r'business', re.I))
        )
        
        for elem in listing_elements:
            try:
                # Find business name link (usually an <a> tag with business name)
                name_link = (
                    elem.find('a', class_=re.compile(r'business.*name|name|business-link', re.I)) or
                    elem.find('a', href=re.compile(r'/biz/', re.I)) or
                    elem.find('h2') or
                    elem.find('h3') or
                    elem.find('a', class_=re.compile(r'link', re.I))
                )
                
                if not name_link:
                    continue
                
                business_name = name_link.get_text(strip=True)
                if not business_name:
                    continue
                
                # Extract profile URL
                profile_url = None
                href = name_link.get('href', '')
                
                if href:
                    if href.startswith('/'):
                        profile_url = urljoin(self.BASE_URL, href)
                    elif 'yellowpages.com' in href:
                        profile_url = href
                
                # Alternative: look for any /biz/ link in the listing
                if not profile_url:
                    biz_link = elem.find('a', href=re.compile(r'/biz/', re.I))
                    if biz_link:
                        href = biz_link.get('href', '')
                        if href:
                            profile_url = urljoin(self.BASE_URL, href) if href.startswith('/') else href
                
                # Clean business name
                business_name = re.sub(r'^\d+\.\s*', '', business_name)
                business_name = business_name.split('\n')[0].strip()
                
                if business_name and len(business_name) > 2:
                    listings.append({
                        'name': business_name,
                        'profile_url': profile_url
                    })
                    
            except Exception as e:
                logger.debug(f"Error parsing listing element: {e}")
                continue
        
        return listings
    
    async def _scrape_detail_page(self, listing: Dict[str, str]) -> Optional[Dict[str, str]]:
        """
        Scrape business detail page to get website URL and other info.
        This is where most websites are found.
        """
        business_name = listing.get('name', '')
        profile_url = listing.get('profile_url')
        
        if not profile_url:
            # No profile URL, return basic info
            return {
                'business_name': business_name,
                'website': ''
            }
        
        try:
            # Fetch detail page using ScrapingBee (if enabled) or direct HTTP
            if USE_SCRAPINGBEE:
                try:
                    client = get_scrapingbee_client()
                    html = await client.fetch_url(
                        url=profile_url,
                        render_js=False,
                        country_code="us",
                        premium_proxy=True,
                        timeout=30000,
                        retries=3
                    )
                except Exception as e:
                    logger.error(f"ScrapingBee error for detail page: {e}")
                    html = None
            else:
                # Fallback: Direct HTTP
                headers = get_headers()
                headers.update({
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Referer": f"{self.BASE_URL}/search",
                    "Upgrade-Insecure-Requests": "1",
                })
                html = await self.fetch_page(profile_url, headers=headers)
            
            if not html:
                logger.debug(f"Failed to fetch detail page for {business_name}")
                return {
                    'business_name': business_name,
                    'website': ''
                }
            
            # Parse detail page
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract website URL (most important)
            website = self._extract_website_from_detail(soup, profile_url)
            
            return {
                'business_name': business_name,
                'website': website or ''
            }
            
        except Exception as e:
            logger.error(f"Error scraping detail page for {business_name}: {e}")
            return {
                'business_name': business_name,
                'website': ''
            }
    
    def _extract_website_from_detail(self, soup: BeautifulSoup, profile_url: str) -> Optional[str]:
        """
        Extract website URL from business detail page.
        YellowPages shows websites in various places on detail pages.
        """
        website = None
        
        # Method 1: Look for website link button/link
        website_elem = (
            soup.find('a', class_=re.compile(r'website|web.*site|visit.*website|web', re.I)) or
            soup.find('a', href=re.compile(r'^https?://(?!www\.yellowpages\.com)', re.I)) or
            soup.find('a', {'data-track': re.compile(r'website', re.I)}) or
            soup.find('a', string=re.compile(r'website|visit.*site|www\.', re.I))
        )
        
        if website_elem and website_elem.get('href'):
            href = website_elem['href']
            # Skip YellowPages internal links
            if 'yellowpages.com' not in href or '/biz/' in href and 'yellowpages.com' in href:
                # This might be a redirect, check the actual href
                pass
            else:
                website = href
        
        # Method 2: Look for website in structured data
        if not website:
            scripts = soup.find_all('script', type='application/ld+json')
            for script in scripts:
                try:
                    import json
                    script_content = script.string if script.string else script.get_text()
                    if script_content:
                        data = json.loads(script_content)
                        if isinstance(data, dict):
                            website = data.get('url') or data.get('website') or data.get('sameAs')
                            if website:
                                break
                except (json.JSONDecodeError, AttributeError):
                    pass
        
        # Method 3: Extract from text using regex (fallback)
        if not website:
            text = soup.get_text()
            url_pattern = re.compile(r'https?://(?!www\.yellowpages\.com|maps\.google)[^\s<>"()]+', re.I)
            urls = url_pattern.findall(text)
            # Filter out common non-website URLs
            for url in urls:
                if not any(x in url.lower() for x in ['facebook.com', 'twitter.com', 'linkedin.com', 'instagram.com']):
                    website = url
                    break
        
        # Clean website URL
        if website:
            website = website.strip()
            # Remove trailing punctuation
            website = re.sub(r'[.,;:]$', '', website)
        
        return website
