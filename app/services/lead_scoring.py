"""
AI-Powered Lead Scoring and Enrichment Service
"""

import json
import re
from typing import Any, Dict, List, Optional
from datetime import datetime
from openai import AsyncOpenAI

from app.core.config import settings


class LeadScoringEngine:
    """
    AI-powered lead scoring with multiple scoring dimensions
    """

    def __init__(self):
        self.openai = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

        # Scoring weights (customizable)
        self.weights = {
            "fit_score": 0.35,      # How well they fit your ICP
            "intent_score": 0.30,   # Buying intent signals
            "engagement_score": 0.20,  # Website engagement
            "data_quality": 0.15    # Completeness of data
        }

        # Ideal Customer Profile (default - should be customizable)
        self.icp = {
            "company_sizes": ["11-50", "51-200", "201-500"],
            "industries": ["technology", "software", "saas", "fintech", "healthcare tech"],
            "technologies": ["react", "python", "aws", "kubernetes", "docker"],
            "locations": ["united states", "canada", "united kingdom"],
            "min_employee_count": 10,
            "max_employee_count": 500
        }

    async def score_lead(self, lead_data: Dict) -> Dict[str, Any]:
        """
        Calculate comprehensive lead score

        Returns:
            Dictionary with scores and explanations
        """
        # Calculate individual scores
        fit_score = await self._calculate_fit_score(lead_data)
        intent_score = await self._calculate_intent_score(lead_data)
        engagement_score = self._calculate_engagement_score(lead_data)
        data_quality_score = self._calculate_data_quality(lead_data)

        # Calculate weighted total
        total_score = (
            fit_score * self.weights["fit_score"] +
            intent_score * self.weights["intent_score"] +
            engagement_score * self.weights["engagement_score"] +
            data_quality_score * self.weights["data_quality"]
        )

        # Determine grade
        grade = self._score_to_grade(total_score)

        # Generate AI explanation
        explanation = await self._generate_score_explanation(
            lead_data, total_score, fit_score, intent_score
        )

        return {
            "total_score": round(total_score, 1),
            "grade": grade,
            "breakdown": {
                "fit_score": round(fit_score, 1),
                "intent_score": round(intent_score, 1),
                "engagement_score": round(engagement_score, 1),
                "data_quality": round(data_quality_score, 1)
            },
            "explanation": explanation,
            "priority": self._get_priority(total_score),
            "recommended_action": self._get_recommended_action(total_score, lead_data),
            "scored_at": datetime.utcnow().isoformat()
        }

    async def _calculate_fit_score(self, lead_data: Dict) -> float:
        """Calculate how well lead fits ICP using AI"""

        prompt = f"""Score this lead's fit with the Ideal Customer Profile (0-100):

LEAD DATA:
{json.dumps(lead_data, indent=2)}

IDEAL CUSTOMER PROFILE:
{json.dumps(self.icp, indent=2)}

Consider:
- Company size match
- Industry alignment
- Technology stack overlap
- Geographic location
- Business model compatibility

Return ONLY a JSON object with:
{{"score": <number>, "factors": [<list of scoring factors>]}}"""

        try:
            response = await self.openai.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1
            )

            content = response.choices[0].message.content
            content = re.sub(r'```json\s*', '', content)
            content = re.sub(r'```\s*', '', content)
            result = json.loads(content)

            return min(100, max(0, result.get("score", 50)))

        except Exception:
            return 50  # Default middle score on error

    async def _calculate_intent_score(self, lead_data: Dict) -> float:
        """Calculate buying intent signals using AI"""

        prompt = f"""Analyze this lead for buying intent signals (score 0-100):

LEAD DATA:
{json.dumps(lead_data, indent=2)}

Intent signals to look for:
- Pain points mentioned
- Technology evaluation
- Budget indicators
- Timeline urgency
- Decision maker status
- Competitor mentions
- Growth indicators

Return ONLY a JSON object with:
{{"score": <number>, "signals": [<list of intent signals found>]}}"""

        try:
            response = await self.openai.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1
            )

            content = response.choices[0].message.content
            content = re.sub(r'```json\s*', '', content)
            content = re.sub(r'```\s*', '', content)
            result = json.loads(content)

            return min(100, max(0, result.get("score", 30)))

        except Exception:
            return 30  # Default lower score for intent

    def _calculate_engagement_score(self, lead_data: Dict) -> float:
        """Calculate score based on engagement data"""
        score = 50  # Base score

        # Website has multiple pages crawled
        if lead_data.get("pages_crawled", 0) > 5:
            score += 10

        # Has social media presence
        social = lead_data.get("social_links", {})
        if social.get("linkedin"):
            score += 15
        if social.get("twitter"):
            score += 5

        # Recent activity indicators
        if lead_data.get("blog_posts"):
            score += 10

        # Job postings (growth signal)
        if lead_data.get("job_postings"):
            score += 10

        return min(100, score)

    def _calculate_data_quality(self, lead_data: Dict) -> float:
        """Calculate data completeness score"""
        required_fields = [
            "company_name", "website", "industry", "contact_email",
            "contact_phone", "contact_name", "address"
        ]

        optional_fields = [
            "company_size", "technologies", "social_links",
            "description", "key_people", "funding_info"
        ]

        # Count filled required fields
        required_filled = sum(1 for f in required_fields if lead_data.get(f))
        required_score = (required_filled / len(required_fields)) * 70

        # Count filled optional fields
        optional_filled = sum(1 for f in optional_fields if lead_data.get(f))
        optional_score = (optional_filled / len(optional_fields)) * 30

        return required_score + optional_score

    async def _generate_score_explanation(
        self,
        lead_data: Dict,
        total_score: float,
        fit_score: float,
        intent_score: float
    ) -> str:
        """Generate human-readable explanation of the score"""

        prompt = f"""Write a brief (2-3 sentence) explanation of why this lead received a score of {total_score}/100.

Key scores:
- Fit Score: {fit_score}/100
- Intent Score: {intent_score}/100

Lead: {lead_data.get('company_name', 'Unknown Company')}
Industry: {lead_data.get('industry', 'Unknown')}

Focus on the most important factors that influenced the score."""

        try:
            response = await self.openai.chat.completions.create(
                model="gpt-4o-mini",  # Use faster model for explanations
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=150
            )

            return response.choices[0].message.content.strip()

        except Exception:
            return f"Lead scored {total_score}/100 based on fit and intent analysis."

    def _score_to_grade(self, score: float) -> str:
        """Convert numeric score to letter grade"""
        if score >= 90:
            return "A+"
        elif score >= 80:
            return "A"
        elif score >= 70:
            return "B"
        elif score >= 60:
            return "C"
        elif score >= 50:
            return "D"
        else:
            return "F"

    def _get_priority(self, score: float) -> str:
        """Get priority level based on score"""
        if score >= 80:
            return "hot"
        elif score >= 60:
            return "warm"
        elif score >= 40:
            return "cool"
        else:
            return "cold"

    def _get_recommended_action(self, score: float, lead_data: Dict) -> str:
        """Get recommended next action"""
        if score >= 80:
            if lead_data.get("contact_phone"):
                return "Call immediately - high priority lead"
            return "Send personalized email within 24 hours"
        elif score >= 60:
            return "Add to email nurture sequence"
        elif score >= 40:
            return "Research further before outreach"
        else:
            return "Low priority - monitor for changes"

    async def batch_score(self, leads: List[Dict]) -> List[Dict]:
        """Score multiple leads"""
        results = []
        for lead in leads:
            score_result = await self.score_lead(lead)
            lead["scoring"] = score_result
            results.append(lead)
        return results

    def update_icp(self, new_icp: Dict):
        """Update Ideal Customer Profile"""
        self.icp.update(new_icp)


class LeadEnrichmentService:
    """
    Enrich leads with additional data from various sources
    """

    def __init__(self):
        self.openai = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    async def enrich_lead(self, lead_data: Dict) -> Dict:
        """
        Enrich lead with additional information
        """
        enriched = lead_data.copy()

        # Extract emails from text content
        if lead_data.get("raw_content"):
            emails = self._extract_emails(lead_data["raw_content"])
            if emails and not enriched.get("contact_email"):
                enriched["contact_email"] = emails[0]
            enriched["all_emails"] = emails

            # Extract phone numbers
            phones = self._extract_phones(lead_data["raw_content"])
            if phones and not enriched.get("contact_phone"):
                enriched["contact_phone"] = phones[0]
            enriched["all_phones"] = phones

        # Detect technologies
        if lead_data.get("raw_content"):
            enriched["technologies"] = await self._detect_technologies(
                lead_data.get("raw_content", ""),
                lead_data.get("website", "")
            )

        # Estimate company size
        if not enriched.get("company_size"):
            enriched["company_size"] = await self._estimate_company_size(lead_data)

        # Generate personalized talking points
        enriched["talking_points"] = await self._generate_talking_points(enriched)

        # Add enrichment metadata
        enriched["enrichment"] = {
            "enriched_at": datetime.utcnow().isoformat(),
            "fields_added": self._count_new_fields(lead_data, enriched),
            "confidence": self._calculate_confidence(enriched)
        }

        return enriched

    def _extract_emails(self, text: str) -> List[str]:
        """Extract email addresses from text"""
        pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        emails = re.findall(pattern, text)

        # Filter out common non-contact emails
        filtered = [
            e for e in emails
            if not any(x in e.lower() for x in ['example', 'test', 'noreply', 'no-reply'])
        ]

        return list(set(filtered))

    def _extract_phones(self, text: str) -> List[str]:
        """Extract phone numbers from text"""
        patterns = [
            r'\+?1?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',
            r'\d{3}[-.\s]\d{3}[-.\s]\d{4}'
        ]

        phones = []
        for pattern in patterns:
            matches = re.findall(pattern, text)
            phones.extend(matches)

        return list(set(phones))

    async def _detect_technologies(self, content: str, website: str) -> List[str]:
        """Detect technologies used by the company"""

        tech_keywords = {
            "languages": ["python", "javascript", "typescript", "java", "go", "rust", "php", "ruby"],
            "frameworks": ["react", "angular", "vue", "django", "flask", "nextjs", "rails", "laravel"],
            "cloud": ["aws", "azure", "gcp", "google cloud", "heroku", "vercel", "netlify"],
            "databases": ["postgresql", "mysql", "mongodb", "redis", "elasticsearch"],
            "devops": ["docker", "kubernetes", "terraform", "jenkins", "github actions"],
            "analytics": ["google analytics", "mixpanel", "amplitude", "segment", "hotjar"]
        }

        detected = []
        content_lower = content.lower()

        for category, techs in tech_keywords.items():
            for tech in techs:
                if tech in content_lower:
                    detected.append(tech)

        return list(set(detected))

    async def _estimate_company_size(self, lead_data: Dict) -> str:
        """Estimate company size using AI"""

        prompt = f"""Based on this information, estimate the company size:

Company: {lead_data.get('company_name', 'Unknown')}
Website: {lead_data.get('website', 'Unknown')}
Description: {lead_data.get('description', 'N/A')}
Technologies: {lead_data.get('technologies', [])}

Return ONLY one of these exact strings:
- "1-10" (startup/micro)
- "11-50" (small)
- "51-200" (medium)
- "201-500" (large)
- "500+" (enterprise)"""

        try:
            response = await self.openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=20
            )

            return response.choices[0].message.content.strip().strip('"')

        except Exception:
            return "Unknown"

    async def _generate_talking_points(self, lead_data: Dict) -> List[str]:
        """Generate personalized talking points for outreach"""

        prompt = f"""Generate 3 personalized talking points for reaching out to this lead:

Company: {lead_data.get('company_name', 'Unknown')}
Industry: {lead_data.get('industry', 'Unknown')}
Description: {lead_data.get('description', 'N/A')}
Pain Points: {lead_data.get('pain_points', [])}
Technologies: {lead_data.get('technologies', [])}

Make them specific, actionable, and relevant to their business.
Return as a JSON array of strings."""

        try:
            response = await self.openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
                max_tokens=300
            )

            content = response.choices[0].message.content
            content = re.sub(r'```json\s*', '', content)
            content = re.sub(r'```\s*', '', content)

            return json.loads(content)

        except Exception:
            return ["Introduce your solution", "Ask about their current challenges", "Offer a demo"]

    def _count_new_fields(self, original: Dict, enriched: Dict) -> int:
        """Count fields added during enrichment"""
        original_keys = set(k for k, v in original.items() if v)
        enriched_keys = set(k for k, v in enriched.items() if v)
        return len(enriched_keys - original_keys)

    def _calculate_confidence(self, enriched: Dict) -> float:
        """Calculate enrichment confidence score"""
        # Based on data completeness and source reliability
        score = 50  # Base

        if enriched.get("contact_email"):
            score += 15
        if enriched.get("contact_phone"):
            score += 10
        if enriched.get("technologies"):
            score += 10
        if enriched.get("company_size"):
            score += 10
        if enriched.get("social_links"):
            score += 5

        return min(100, score)


# Singleton instances
scoring_engine = LeadScoringEngine()
enrichment_service = LeadEnrichmentService()
