"""
Firecrawl-style Web Scraping Engine with LLM Extraction
Supports multiple modes: single, crawl, map, and search
"""

import asyncio
import hashlib
import json
import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings


class FirecrawlScraper:
    """
    Advanced web scraper with Firecrawl-style capabilities
    """

    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=settings.SCRAPE_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": settings.USER_AGENT}
        )
        self.openai = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.visited_urls: Set[str] = set()
        self.semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_SCRAPES)

    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()

    # ============================================
    # SCRAPING MODES
    # ============================================

    async def scrape_single(
        self,
        url: str,
        extraction_schema: Optional[Dict] = None,
        include_raw: bool = True,
        clean_content: bool = True
    ) -> Dict[str, Any]:
        """
        Scrape a single URL and optionally extract structured data

        Args:
            url: Target URL to scrape
            extraction_schema: JSON schema for LLM extraction
            include_raw: Include raw HTML in response
            clean_content: Convert to clean markdown
        """
        job_id = str(uuid.uuid4())

        try:
            # Fetch page content
            html, metadata = await self._fetch_page(url)

            # Clean and convert content
            markdown = self._html_to_markdown(html) if clean_content else None
            text = self._extract_text(html)

            # Extract structured data if schema provided
            extracted_data = None
            if extraction_schema:
                extracted_data = await self._llm_extract(text, extraction_schema, url)

            # Auto-detect lead information
            lead_data = await self._extract_lead_info(text, url)

            return {
                "job_id": job_id,
                "success": True,
                "url": url,
                "metadata": metadata,
                "content": {
                    "markdown": markdown,
                    "text": text[:10000],  # Truncate for response
                    "raw_html": html if include_raw else None
                },
                "extracted_data": extracted_data,
                "lead_info": lead_data,
                "scraped_at": datetime.utcnow().isoformat()
            }

        except Exception as e:
            return {
                "job_id": job_id,
                "success": False,
                "url": url,
                "error": str(e),
                "scraped_at": datetime.utcnow().isoformat()
            }

    async def crawl_site(
        self,
        start_url: str,
        max_pages: int = 50,
        extraction_schema: Optional[Dict] = None,
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Crawl an entire website starting from a URL

        Args:
            start_url: Starting URL
            max_pages: Maximum pages to crawl
            extraction_schema: Schema for data extraction
            include_patterns: URL patterns to include
            exclude_patterns: URL patterns to exclude
            progress_callback: Callback for progress updates
        """
        job_id = str(uuid.uuid4())
        self.visited_urls = set()
        results = []
        queue = [start_url]
        base_domain = urlparse(start_url).netloc

        while queue and len(results) < max_pages:
            # Process batch
            batch = queue[:settings.MAX_CONCURRENT_SCRAPES]
            queue = queue[settings.MAX_CONCURRENT_SCRAPES:]

            tasks = []
            for url in batch:
                if url not in self.visited_urls:
                    self.visited_urls.add(url)
                    tasks.append(self._crawl_page(url, extraction_schema))

            # Execute batch
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in batch_results:
                if isinstance(result, dict) and result.get("success"):
                    results.append(result)

                    # Extract new URLs
                    for link in result.get("links", []):
                        if self._should_crawl(link, base_domain, include_patterns, exclude_patterns):
                            if link not in self.visited_urls:
                                queue.append(link)

                    # Progress callback
                    if progress_callback:
                        await progress_callback(len(results), max_pages)

            # Rate limiting
            await asyncio.sleep(settings.RATE_LIMIT_DELAY)

        return {
            "job_id": job_id,
            "success": True,
            "start_url": start_url,
            "pages_crawled": len(results),
            "results": results,
            "completed_at": datetime.utcnow().isoformat()
        }

    async def map_site(
        self,
        url: str,
        max_pages: int = 100
    ) -> Dict[str, Any]:
        """
        Create a sitemap of all URLs on a website

        Args:
            url: Target website URL
            max_pages: Maximum pages to discover
        """
        job_id = str(uuid.uuid4())
        self.visited_urls = set()
        site_map = []
        queue = [url]
        base_domain = urlparse(url).netloc

        while queue and len(site_map) < max_pages:
            current_url = queue.pop(0)
            if current_url in self.visited_urls:
                continue

            self.visited_urls.add(current_url)

            try:
                html, metadata = await self._fetch_page(current_url)
                soup = BeautifulSoup(html, 'lxml')

                # Get page info
                page_info = {
                    "url": current_url,
                    "title": metadata.get("title", ""),
                    "depth": self._get_url_depth(current_url, url),
                    "type": self._classify_page_type(current_url, soup)
                }
                site_map.append(page_info)

                # Find links
                for link in soup.find_all('a', href=True):
                    href = urljoin(current_url, link['href'])
                    parsed = urlparse(href)
                    if parsed.netloc == base_domain and href not in self.visited_urls:
                        queue.append(href.split('#')[0])  # Remove fragments

            except Exception:
                continue

            await asyncio.sleep(settings.RATE_LIMIT_DELAY / 2)

        return {
            "job_id": job_id,
            "success": True,
            "url": url,
            "total_pages": len(site_map),
            "sitemap": site_map,
            "completed_at": datetime.utcnow().isoformat()
        }

    async def search_and_scrape(
        self,
        query: str,
        num_results: int = 10,
        extraction_schema: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Search for leads based on query and scrape results

        Args:
            query: Search query
            num_results: Number of results to scrape
            extraction_schema: Schema for data extraction
        """
        job_id = str(uuid.uuid4())

        # Use DuckDuckGo for search (free, no API key needed)
        search_url = f"https://html.duckduckgo.com/html/?q={query}"

        try:
            html, _ = await self._fetch_page(search_url)
            soup = BeautifulSoup(html, 'lxml')

            # Extract search results
            results = []
            for result in soup.select('.result__a')[:num_results]:
                url = result.get('href', '')
                if url.startswith('//'):
                    url = 'https:' + url

                # Scrape each result
                scraped = await self.scrape_single(url, extraction_schema)
                if scraped.get("success"):
                    results.append(scraped)

                await asyncio.sleep(settings.RATE_LIMIT_DELAY)

            return {
                "job_id": job_id,
                "success": True,
                "query": query,
                "results_found": len(results),
                "results": results,
                "completed_at": datetime.utcnow().isoformat()
            }

        except Exception as e:
            return {
                "job_id": job_id,
                "success": False,
                "query": query,
                "error": str(e)
            }

    # ============================================
    # LLM EXTRACTION
    # ============================================

    async def _llm_extract(
        self,
        text: str,
        schema: Dict,
        url: str
    ) -> Dict[str, Any]:
        """Extract structured data from text using LLM"""

        system_prompt = """You are a data extraction expert. Extract information from the provided text according to the given schema.
Return ONLY valid JSON matching the schema exactly. If information is not found, use null for that field."""

        user_prompt = f"""Extract data from this webpage content according to the schema below.

URL: {url}

SCHEMA:
{json.dumps(schema, indent=2)}

CONTENT:
{text[:8000]}

Return ONLY the extracted JSON data, no explanations."""

        try:
            response = await self.openai.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=settings.LLM_TEMPERATURE,
                max_tokens=settings.LLM_MAX_TOKENS
            )

            content = response.choices[0].message.content
            # Clean JSON from markdown code blocks
            content = re.sub(r'```json\s*', '', content)
            content = re.sub(r'```\s*', '', content)

            return json.loads(content)

        except Exception as e:
            return {"error": f"Extraction failed: {str(e)}"}

    async def _extract_lead_info(self, text: str, url: str) -> Dict[str, Any]:
        """Auto-extract common lead information"""

        schema = {
            "company_name": "string - Company or business name",
            "industry": "string - Industry or sector",
            "description": "string - Brief company description (1-2 sentences)",
            "contact_email": "string - Contact email address",
            "contact_phone": "string - Contact phone number",
            "address": "string - Physical address",
            "social_links": {
                "linkedin": "string - LinkedIn URL",
                "twitter": "string - Twitter URL",
                "facebook": "string - Facebook URL"
            },
            "technologies": "array - List of technologies/tools mentioned",
            "pain_points": "array - Potential business pain points or needs identified",
            "company_size": "string - Company size indicator (startup, SMB, enterprise)",
            "key_people": "array - Names and titles of key people mentioned"
        }

        return await self._llm_extract(text, schema, url)

    # ============================================
    # HELPER METHODS
    # ============================================

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _fetch_page(self, url: str) -> tuple[str, Dict]:
        """Fetch page content with retries"""
        async with self.semaphore:
            response = await self.client.get(url)
            response.raise_for_status()

            html = response.text
            soup = BeautifulSoup(html, 'lxml')

            metadata = {
                "title": soup.title.string if soup.title else "",
                "description": "",
                "status_code": response.status_code,
                "content_type": response.headers.get("content-type", ""),
                "content_length": len(html)
            }

            # Extract meta description
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            if meta_desc:
                metadata["description"] = meta_desc.get('content', '')

            return html, metadata

    async def _crawl_page(self, url: str, schema: Optional[Dict]) -> Dict:
        """Crawl a single page and extract links"""
        result = await self.scrape_single(url, schema, include_raw=False)

        if result.get("success"):
            # Extract links from the page
            try:
                html, _ = await self._fetch_page(url)
                soup = BeautifulSoup(html, 'lxml')
                links = []
                for link in soup.find_all('a', href=True):
                    href = urljoin(url, link['href'])
                    links.append(href.split('#')[0])
                result["links"] = list(set(links))
            except Exception:
                result["links"] = []

        return result

    def _html_to_markdown(self, html: str) -> str:
        """Convert HTML to clean markdown"""
        soup = BeautifulSoup(html, 'lxml')

        # Remove unwanted elements
        for tag in soup.find_all(['script', 'style', 'nav', 'footer', 'header', 'aside']):
            tag.decompose()

        # Convert to text with basic formatting
        text = soup.get_text(separator='\n', strip=True)

        # Clean up whitespace
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        return '\n\n'.join(lines)

    def _extract_text(self, html: str) -> str:
        """Extract clean text from HTML"""
        soup = BeautifulSoup(html, 'lxml')

        # Remove unwanted elements
        for tag in soup.find_all(['script', 'style', 'nav', 'footer']):
            tag.decompose()

        return soup.get_text(separator=' ', strip=True)

    def _should_crawl(
        self,
        url: str,
        base_domain: str,
        include_patterns: Optional[List[str]],
        exclude_patterns: Optional[List[str]]
    ) -> bool:
        """Check if URL should be crawled"""
        parsed = urlparse(url)

        # Must be same domain
        if parsed.netloc != base_domain:
            return False

        # Check exclude patterns
        if exclude_patterns:
            for pattern in exclude_patterns:
                if re.search(pattern, url):
                    return False

        # Check include patterns
        if include_patterns:
            for pattern in include_patterns:
                if re.search(pattern, url):
                    return True
            return False

        # Exclude common non-content pages
        exclude_extensions = ['.pdf', '.jpg', '.png', '.gif', '.css', '.js', '.zip']
        if any(url.lower().endswith(ext) for ext in exclude_extensions):
            return False

        return True

    def _get_url_depth(self, url: str, base_url: str) -> int:
        """Calculate URL depth relative to base"""
        base_path = urlparse(base_url).path.rstrip('/')
        url_path = urlparse(url).path.rstrip('/')

        if base_path:
            url_path = url_path.replace(base_path, '', 1)

        return len([p for p in url_path.split('/') if p])

    def _classify_page_type(self, url: str, soup: BeautifulSoup) -> str:
        """Classify the type of page"""
        url_lower = url.lower()
        title = soup.title.string.lower() if soup.title else ""

        if any(x in url_lower for x in ['contact', 'about', 'team']):
            return "contact"
        elif any(x in url_lower for x in ['blog', 'news', 'article']):
            return "content"
        elif any(x in url_lower for x in ['product', 'service', 'solution']):
            return "product"
        elif any(x in url_lower for x in ['pricing', 'plan']):
            return "pricing"
        elif url_lower.endswith('/') or url_lower.endswith('.html'):
            return "page"
        else:
            return "other"


class LeadDiscoveryEngine:
    """
    Advanced lead discovery using multiple strategies
    """

    def __init__(self):
        self.scraper = FirecrawlScraper()
        self.openai = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    async def close(self):
        await self.scraper.close()

    async def discover_by_industry(
        self,
        industry: str,
        location: str,
        num_leads: int = 20
    ) -> List[Dict]:
        """Discover leads by industry and location"""

        queries = [
            f"{industry} companies in {location}",
            f"top {industry} businesses {location}",
            f"{industry} startups {location}",
            f"best {industry} services {location}"
        ]

        all_leads = []
        for query in queries:
            result = await self.scraper.search_and_scrape(query, num_results=num_leads // len(queries))
            if result.get("success"):
                for r in result.get("results", []):
                    if r.get("lead_info"):
                        all_leads.append({
                            "source_url": r.get("url"),
                            "source_query": query,
                            **r.get("lead_info", {})
                        })

        return all_leads[:num_leads]

    async def discover_from_directory(
        self,
        directory_url: str,
        max_listings: int = 50
    ) -> List[Dict]:
        """Scrape leads from a business directory"""

        # Crawl the directory
        crawl_result = await self.scraper.crawl_site(
            directory_url,
            max_pages=max_listings,
            include_patterns=[r'/company/', r'/business/', r'/listing/']
        )

        leads = []
        for page in crawl_result.get("results", []):
            if page.get("lead_info"):
                leads.append(page["lead_info"])

        return leads

    async def enrich_lead(self, lead_data: Dict) -> Dict:
        """Enrich lead with additional information"""

        # If we have a website, scrape it for more info
        if lead_data.get("website"):
            result = await self.scraper.scrape_single(lead_data["website"])
            if result.get("success") and result.get("lead_info"):
                # Merge with existing data
                for key, value in result["lead_info"].items():
                    if value and not lead_data.get(key):
                        lead_data[key] = value

        # Generate AI insights
        lead_data["ai_insights"] = await self._generate_insights(lead_data)

        return lead_data

    async def _generate_insights(self, lead_data: Dict) -> Dict:
        """Generate AI-powered insights about a lead"""

        prompt = f"""Analyze this lead data and provide insights:

{json.dumps(lead_data, indent=2)}

Provide:
1. Lead quality score (1-100)
2. Best approach for outreach
3. Potential pain points to address
4. Recommended talking points
5. Risk factors

Return as JSON."""

        try:
            response = await self.openai.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )

            content = response.choices[0].message.content
            content = re.sub(r'```json\s*', '', content)
            content = re.sub(r'```\s*', '', content)

            return json.loads(content)

        except Exception:
            return {}


# Singleton instances
scraper = FirecrawlScraper()
discovery_engine = LeadDiscoveryEngine()
