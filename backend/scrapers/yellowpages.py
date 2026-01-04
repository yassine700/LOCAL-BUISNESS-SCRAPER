"""
YellowPages scraper with pagination and detail page crawling.
Uses optional proxy API for residential proxy and anti-bot protection.
Supports direct IP scraping or proxy-based scraping via any service.
"""
import re
import random
import asyncio
from typing import List, Dict, Optional
from urllib.parse import quote, urljoin
from bs4 import BeautifulSoup
import logging

from backend.scrapers.base import BaseScraper
from backend.config import get_headers, USE_PROXY, MAX_PAGES
# Note: USE_PROXY is now a function, call it as USE_PROXY()
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
    # Domains to filter out from website extraction (social media, aggregators, etc.)
    BLOCKED_DOMAINS = [
        'facebook.com', 'twitter.com', 'instagram.com', 'linkedin.com',
        'tiktok.com', 'youtube.com', 'yellowpages.com', 'maps.google.com',
        'yelp.com', 'google.com', 'bizapedia.com', 'pinterest.com',
        'snapchat.com', 'reddit.com', 'nextdoor.com', 'foursquare.com'
    ]    
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
            logger.info(f"[FORENSIC] Page {page} URL: {url}")
            logger.info(f"[FORENSIC] Search params: keyword='{keyword}', city='{normalized_city}' (normalized from '{city}')")
            
            logger.info(f"Fetching page {page} for {normalized_city}")
            
            # Get listing page (with circuit breaker)
            html = await self._fetch_listing_page_with_circuit_breaker(
                url, 
                job_id=job_id, 
                keyword=keyword, 
                city=normalized_city
            )
            if not html:
                logger.error(f"[FORENSIC] FAILED to fetch page {page} for {normalized_city} - HTML is None")
                logger.error(f"[FORENSIC] This breaks the pipeline - no HTML means no parsing possible")
                break
            
            # Parse listings from this page
            listings = self._parse_listing_page(html)
            logger.info(f"[PIPELINE DEBUG] Page {page} parsed: {len(listings)} listings found for {normalized_city}")
            
            # FORENSIC DEBUG: Log page loop execution
            logger.info(f"[FORENSIC] Page {page} loop: HTML length={len(html)}, listings={len(listings)}")
            
            if not listings:
                logger.warning(f"[FORENSIC] ZERO LISTINGS on page {page} for {normalized_city} - stopping pagination")
                logger.warning(f"[FORENSIC] This may indicate: blocking, invalid search, or page structure change")
                break
            
            logger.info(f"Found {len(listings)} listings on page {page}")
            
            # FORENSIC DEBUG: Log detail page loop start
            logger.info(f"[FORENSIC] Starting detail page loop: {len(listings)} listings to process")
            
            # Step 2: For each listing, visit detail page to get website
            detail_page_count = 0
            for listing in listings:
                detail_page_count += 1
                logger.debug(f"[FORENSIC] Processing listing {detail_page_count}/{len(listings)}: {listing.get('name', 'unknown')[:50]}")
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
                
                # FORENSIC DEBUG: Log detail page fetch attempt
                profile_url = listing.get('profile_url', 'NO URL')
                logger.debug(f"[FORENSIC] Fetching detail page {detail_page_count}/{len(listings)}: {profile_url}")
                
                business_data = await self._scrape_detail_page(listing)
                
                # FORENSIC DEBUG: Log business data extraction result
                if business_data:
                    logger.info(f"[FORENSIC] Business data extracted: name='{business_data.get('business_name', 'NONE')}', website='{business_data.get('website', 'NONE')}', method='{business_data.get('extraction_method', 'NONE')}'")
                    all_businesses.append(business_data)
                    # Call callback if provided (for real-time updates)
                    if on_business_scraped:
                        logger.info(f"[PIPELINE DEBUG] Calling callback for business: {business_data.get('business_name', 'unknown')} (page {page}, city {normalized_city})")
                        on_business_scraped(business_data, False, page, normalized_city)
                    else:
                        logger.warning(f"[PIPELINE DEBUG] No callback provided - business {business_data.get('business_name', 'unknown')} will not be emitted")
                else:
                    logger.warning(f"[FORENSIC] NO BUSINESS DATA extracted from listing {detail_page_count} on page {page} - detail page parsing failed")
            
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
    
    def _validate_domain(self, url: str) -> bool:
        """
        Validate that a URL looks like a legitimate business website.
        Filters out social media, aggregators, and other non-business domains.
        
        Args:
            url: URL to validate
            
        Returns:
            True if URL appears to be a business domain, False otherwise
        """
        if not url:
            return False
        
        url_lower = url.lower()
        
        # Filter out blocked domains
        for blocked_domain in self.BLOCKED_DOMAINS:
            if blocked_domain in url_lower:
                return False
        
        # Must look like a URL (start with protocol or www)
        if not url.startswith(('http://', 'https://', 'www.')):
            return False
        
        # Basic sanity check: should have a dot (domain.tld)
        if '.' not in url:
            return False
        
        return True
    
    async def _fetch_listing_page(self, url: str) -> Optional[str]:
        """
        Fetch a listing page using proxy API (if configured) or direct HTTP.
        Falls back to direct HTTP if proxy API fails or is not configured.
        Proxy API can be from any service (ScrapingBee, Bright Data, etc).
        """
        # Try proxy API first if key is configured
        # FIX Bug 1: Call USE_PROXY() function to check runtime-set proxy key
        if USE_PROXY():
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
                if html:
                    logger.debug("Successfully fetched via proxy API")
                    return html
            except Exception as e:
                logger.warning(f"Proxy API request failed: {e}. Falling back to direct HTTP.")
        else:
            logger.debug("Proxy API key not configured. Using direct HTTP request.")
        
        # Fallback: Direct HTTP request (works for most YellowPages requests)
        headers = get_headers()
        headers.update({
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.google.com/" if random.random() > 0.5 else self.BASE_URL,
            "Upgrade-Insecure-Requests": "1",
        })
        
        html = await self.fetch_page(url, headers=headers)
        if html:
            logger.debug("Successfully fetched via direct HTTP")
        return html
    
    async def _fetch_listing_page_with_circuit_breaker(
        self, 
        url: str, 
        job_id: Optional[str] = None,
        keyword: Optional[str] = None,
        city: Optional[str] = None
    ) -> Optional[str]:
        """
        Fetch listing page with circuit breaker logic.
        Tracks 403s and blocks city after 5 consecutive blocks.
        """
        # Check if city is already blocked
        if job_id and keyword and city:
            from backend.database import db
            if db.is_city_blocked(job_id, keyword, city):
                logger.warning(f"City {city} is blocked due to persistent 403s. Skipping.")
                return None
        
        # Attempt to fetch
        html = await self._fetch_listing_page(url)
        
        # Track 403s for circuit breaker
        if html is None:
            if job_id and keyword and city:
                from backend.database import db
                count_403 = db.increment_403_count(job_id, keyword, city)
                
                if count_403 >= 5:
                    db.set_city_blocked(job_id, keyword, city)
                    warning_msg = (
                        f"Circuit breaker triggered for {city}: "
                        f"5 consecutive 403s detected. City marked as blocked. "
                    )
                    # FIX Bug 1: Call USE_PROXY() function to check runtime-set proxy key
                    if USE_PROXY():
                        warning_msg += "Check your proxy API key and settings."
                    else:
                        warning_msg += "Your IP may be blocked. Try adding a proxy API key for better IP rotation."
                    
                    logger.warning(warning_msg)
                    # Emit warning via Redis
                    try:
                        import redis
                        import json
                        from backend.config import REDIS_URL
                        redis_client = redis.from_url(REDIS_URL)
                        warning_event = {
                            "type": "warning",
                            "job_id": job_id,
                            "data": {
                                "city": city,
                                "reason": "persistent_403_blocks",
                                "message": f"City {city} has been blocked after 5 consecutive 403 responses. "
                                          f"This typically means your IP is being actively blocked by YellowPages. "
                                          f"Consider using ScrapingBee with premium residential proxies."
                            }
                        }
                        redis_client.publish(f"job:{job_id}:events", json.dumps(warning_event))
                    except Exception as e:
                        logger.debug(f"Failed to emit circuit breaker warning: {e}")
        else:
            # Success - reset 403 count
            if job_id and keyword and city:
                from backend.database import db
                db.reset_403_count(job_id, keyword, city)
        
        return html
    
    def _parse_listing_page(self, html: str) -> List[Dict[str, str]]:
        """
        Parse listing page to extract business names and profile URLs.
        Returns list of dicts with 'name' and 'profile_url'.
        """
        # FORENSIC DEBUG: Log HTML input
        logger.info(f"[FORENSIC] Parsing listing page: {len(html)} bytes of HTML")
        
        soup = BeautifulSoup(html, 'html.parser')
        listings = []
        
        # FORENSIC DEBUG: Test each selector individually
        selector_results = {}
        selector_results['div.result'] = len(soup.find_all('div', class_=re.compile(r'result', re.I)))
        selector_results['div.srp-listing'] = len(soup.find_all('div', class_=re.compile(r'srp-listing', re.I)))
        selector_results['div.organic'] = len(soup.find_all('div', class_=re.compile(r'organic', re.I)))
        selector_results['article'] = len(soup.find_all('article'))
        selector_results['div[data-testid]'] = len(soup.find_all('div', {'data-testid': re.compile(r'listing|result', re.I)}))
        selector_results['div.business'] = len(soup.find_all('div', class_=re.compile(r'business', re.I)))
        
        logger.info(f"[FORENSIC] Selector match counts: {selector_results}")
        
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
        
        logger.info(f"[FORENSIC] Total listing elements found: {len(listing_elements)}")
        
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
                    logger.debug(f"[FORENSIC] Parsed listing: {business_name[:50]}...")
                else:
                    logger.debug(f"[FORENSIC] Rejected listing: name='{business_name}', len={len(business_name) if business_name else 0}")
                    
            except Exception as e:
                logger.error(f"[FORENSIC] Error parsing listing element: {e}", exc_info=True)
                continue
        
        logger.info(f"[FORENSIC] Final parsed listings count: {len(listings)}")
        if len(listings) == 0:
            # FORENSIC: Dump HTML structure hints
            logger.warning(f"[FORENSIC] ZERO LISTINGS PARSED - HTML structure analysis:")
            logger.warning(f"[FORENSIC] - Title tag: {soup.find('title').get_text()[:100] if soup.find('title') else 'NO TITLE'}")
            logger.warning(f"[FORENSIC] - Body classes: {soup.find('body').get('class') if soup.find('body') else 'NO BODY'}")
            # Check for common YellowPages page indicators
            page_text = soup.get_text()[:500].lower()
            if 'no results' in page_text or 'no businesses' in page_text:
                logger.warning(f"[FORENSIC] Page indicates NO RESULTS")
            if 'try again' in page_text or 'blocked' in page_text:
                logger.warning(f"[FORENSIC] Page may indicate BLOCKING")
        
        return listings
    
    async def _scrape_detail_page(self, listing: Dict[str, str]) -> Optional[Dict[str, str]]:
        """
        Scrape business detail page to get website URL and other info.
        This is where most websites are found.
        """
        business_name = listing.get('name', '')
        profile_url = listing.get('profile_url')
        
        logger.debug(f"[FORENSIC] _scrape_detail_page called: name='{business_name}', url='{profile_url}'")
        
        if not profile_url:
            # No profile URL, return basic info
            logger.debug(f"[FORENSIC] No profile URL for '{business_name}', returning basic info")
            return {
                'business_name': business_name,
                'website': '',
                'extraction_method': 'none'
            }
        
        try:
            # Fetch detail page using proxy API (if enabled) or direct HTTP
            # FIX Bug 1: Call USE_PROXY() function to check runtime-set proxy key
            if USE_PROXY():
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
                    logger.error(f"Proxy API error for detail page: {e}")
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
                logger.warning(f"[FORENSIC] Failed to fetch detail page for {business_name} from {profile_url}")
                return {
                    'business_name': business_name,
                    'website': '',
                    'extraction_method': 'none'
                }
            
            # FORENSIC DEBUG: Log detail page HTML
            logger.debug(f"[FORENSIC] Detail page fetched: {len(html)} bytes for {business_name}")
            
            # Parse detail page
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract website URL with metadata
            extraction_result = self._extract_website_from_detail(soup, profile_url)
            
            return {
                'business_name': business_name,
                'website': extraction_result.get('website', ''),
                'extraction_method': extraction_result.get('extraction_method', 'none')
            }
            
        except Exception as e:
            logger.error(f"Error scraping detail page for {business_name}: {e}")
            return {
                'business_name': business_name,
                'website': '',
                'extraction_method': 'none'
            }
    
    def _extract_website_from_detail(self, soup: BeautifulSoup, profile_url: str) -> Dict[str, str]:
        """
        Extract website URL from business detail page.
        YellowPages shows websites in various places on detail pages.
        
        Returns:
            Dict with 'website' and 'extraction_method' keys
        """
        website = None
        extraction_method = None
        
        # Method 1: Extract from structured data (JSON-LD) — MOST RELIABLE
        # This is the primary method as it contains official business data
        scripts = soup.find_all('script', type='application/ld+json')
        for script in scripts:
            try:
                import json
                script_content = script.string if script.string else script.get_text()
                if script_content:
                    data = json.loads(script_content)
                    if isinstance(data, dict):
                        # Try multiple JSON-LD properties
                        candidate = data.get('url') or data.get('website') or data.get('sameAs')
                        # FIX Bug 2: Check if candidate is a list BEFORE validating as domain
                        # sameAs can be a list in JSON-LD schema
                        if isinstance(candidate, list):
                            # Handle list case (e.g., sameAs can be an array)
                            for url in candidate:
                                if url and isinstance(url, str) and self._validate_domain(url):
                                    website = url
                                    extraction_method = 'json_ld'
                                    break  # Exit inner loop
                            # FIX Bug 1: If we found a valid website from list, exit outer loop too
                            if website:
                                break  # Exit outer loop (iterating scripts)
                        elif candidate and isinstance(candidate, str) and self._validate_domain(candidate):
                            # Handle string case
                            website = candidate
                            extraction_method = 'json_ld'
                            break  # Exit outer loop (iterating scripts)
            except (json.JSONDecodeError, AttributeError, TypeError):
                pass
        
        # Method 2: Look for website link button/link (secondary)
        if not website:
            website_elem = (
                soup.find('a', class_=re.compile(r'website|web.*site|visit.*website|web', re.I)) or
                soup.find('a', href=re.compile(r'^https?://(?!www\.yellowpages\.com)', re.I)) or
                soup.find('a', {'data-track': re.compile(r'website', re.I)}) or
                soup.find('a', string=re.compile(r'website|visit.*site|www\.', re.I))
            )
            
            if website_elem and website_elem.get('href'):
                href = website_elem['href']
                if self._validate_domain(href):
                    website = href
                    extraction_method = 'heuristic'
        
        # Method 3: Extract from text using regex (fallback only)
        if not website:
            text = soup.get_text()
            url_pattern = re.compile(r'https?://[^\s<>"()]+', re.I)
            urls = url_pattern.findall(text)
            for url in urls:
                if self._validate_domain(url):
                    website = url
                    extraction_method = 'regex'
                    break
        
        # Clean website URL
        if website:
            website = website.strip()
            # Remove trailing punctuation
            website = re.sub(r'[.,;:]$', '', website)
            logger.debug(f"[FORENSIC] Website extracted: '{website}' via method '{extraction_method}'")
        else:
            logger.debug(f"[FORENSIC] NO WEBSITE extracted for detail page")
        
        if not website:
            extraction_method = 'none'
        
        # FORENSIC DEBUG: Log final result
        logger.debug(f"[FORENSIC] Website extraction complete: website='{website}', method='{extraction_method}'")
        
        return {
            'website': website or '',
            'extraction_method': extraction_method or 'none'
        }
