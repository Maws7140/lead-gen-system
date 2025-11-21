"""
API Routes for LeadGen Pro
"""

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc

from app.models.database import get_db, Lead, ScrapeJob, Campaign, Activity
from app.services.scraper import scraper, discovery_engine, FirecrawlScraper
from app.services.lead_scoring import scoring_engine, enrichment_service

router = APIRouter()


# ============================================
# SCHEMAS
# ============================================

class ScrapeRequest(BaseModel):
    url: HttpUrl
    mode: str = "single"  # single, crawl, map
    extraction_schema: Optional[Dict] = None
    max_pages: int = 50
    include_patterns: Optional[List[str]] = None
    exclude_patterns: Optional[List[str]] = None


class SearchRequest(BaseModel):
    query: str
    num_results: int = 10
    extraction_schema: Optional[Dict] = None


class LeadCreate(BaseModel):
    company_name: str
    website: Optional[str] = None
    industry: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    source: Optional[str] = "manual"


class LeadUpdate(BaseModel):
    company_name: Optional[str] = None
    website: Optional[str] = None
    industry: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    status: Optional[str] = None


class DiscoveryRequest(BaseModel):
    industry: str
    location: str
    num_leads: int = 20


class CampaignCreate(BaseModel):
    name: str
    description: Optional[str] = None
    campaign_type: str = "email"  # email, sms, multi-channel
    email_subject: Optional[str] = None
    email_template: Optional[str] = None
    sms_template: Optional[str] = None
    lead_filters: Optional[Dict] = None


class BulkImportRequest(BaseModel):
    leads: List[Dict]
    source: str = "bulk_import"
    auto_enrich: bool = True
    auto_score: bool = True


class ExportRequest(BaseModel):
    format: str = "csv"  # csv, json, excel
    filters: Optional[Dict] = None
    fields: Optional[List[str]] = None


# ============================================
# SCRAPING ENDPOINTS
# ============================================

@router.post("/scrape", tags=["Scraping"])
async def scrape_url(request: ScrapeRequest, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    """
    Scrape a URL with optional LLM extraction

    Modes:
    - single: Scrape single page
    - crawl: Crawl entire site
    - map: Create sitemap
    """
    job_id = str(uuid.uuid4())

    # Create job record
    job = ScrapeJob(
        job_id=job_id,
        mode=request.mode,
        url=str(request.url),
        config={
            "max_pages": request.max_pages,
            "extraction_schema": request.extraction_schema
        },
        status="pending",
        started_at=datetime.utcnow()
    )
    db.add(job)
    await db.commit()

    # Execute based on mode
    scraper_instance = FirecrawlScraper()

    try:
        if request.mode == "single":
            result = await scraper_instance.scrape_single(
                str(request.url),
                request.extraction_schema
            )
        elif request.mode == "crawl":
            result = await scraper_instance.crawl_site(
                str(request.url),
                request.max_pages,
                request.extraction_schema,
                request.include_patterns,
                request.exclude_patterns
            )
        elif request.mode == "map":
            result = await scraper_instance.map_site(
                str(request.url),
                request.max_pages
            )
        else:
            raise HTTPException(status_code=400, detail=f"Invalid mode: {request.mode}")

        # Update job
        job.status = "completed" if result.get("success") else "failed"
        job.extracted_data = result
        job.completed_at = datetime.utcnow()
        job.duration_seconds = (job.completed_at - job.started_at).total_seconds()
        await db.commit()

        return result

    except Exception as e:
        job.status = "failed"
        job.error_message = str(e)
        await db.commit()
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        await scraper_instance.close()


@router.post("/search", tags=["Scraping"])
async def search_and_scrape(request: SearchRequest):
    """Search the web and scrape results"""
    scraper_instance = FirecrawlScraper()
    try:
        result = await scraper_instance.search_and_scrape(
            request.query,
            request.num_results,
            request.extraction_schema
        )
        return result
    finally:
        await scraper_instance.close()


@router.get("/scrape/jobs", tags=["Scraping"])
async def list_scrape_jobs(
    status: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db)
):
    """List all scrape jobs"""
    query = select(ScrapeJob).order_by(desc(ScrapeJob.created_at)).limit(limit)
    if status:
        query = query.where(ScrapeJob.status == status)

    result = await db.execute(query)
    jobs = result.scalars().all()

    return [{
        "job_id": j.job_id,
        "mode": j.mode,
        "url": j.url,
        "status": j.status,
        "pages_scraped": j.pages_scraped,
        "duration_seconds": j.duration_seconds,
        "created_at": j.created_at.isoformat() if j.created_at else None
    } for j in jobs]


@router.get("/scrape/job/{job_id}", tags=["Scraping"])
async def get_scrape_job(job_id: str, db: AsyncSession = Depends(get_db)):
    """Get details of a specific scrape job"""
    result = await db.execute(
        select(ScrapeJob).where(ScrapeJob.job_id == job_id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": job.job_id,
        "mode": job.mode,
        "url": job.url,
        "status": job.status,
        "config": job.config,
        "extracted_data": job.extracted_data,
        "error_message": job.error_message,
        "pages_scraped": job.pages_scraped,
        "duration_seconds": job.duration_seconds,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None
    }


# ============================================
# LEAD DISCOVERY ENDPOINTS
# ============================================

@router.post("/discover", tags=["Discovery"])
async def discover_leads(request: DiscoveryRequest, db: AsyncSession = Depends(get_db)):
    """Discover leads by industry and location"""
    leads = await discovery_engine.discover_by_industry(
        request.industry,
        request.location,
        request.num_leads
    )

    # Save leads to database
    saved_leads = []
    for lead_data in leads:
        lead = Lead(
            company_name=lead_data.get("company_name", "Unknown"),
            website=lead_data.get("website"),
            industry=request.industry,
            contact_email=lead_data.get("contact_email"),
            contact_phone=lead_data.get("contact_phone"),
            address=lead_data.get("address"),
            source="discovery",
            source_url=lead_data.get("source_url"),
            ai_summary=lead_data.get("description"),
            technologies=lead_data.get("technologies", []),
            social_profiles=lead_data.get("social_links", {}),
            pain_points=lead_data.get("pain_points", [])
        )
        db.add(lead)
        saved_leads.append(lead)

    await db.commit()

    return {
        "leads_found": len(saved_leads),
        "industry": request.industry,
        "location": request.location,
        "leads": [{"id": l.id, "company_name": l.company_name, "website": l.website} for l in saved_leads]
    }


@router.post("/discover/directory", tags=["Discovery"])
async def discover_from_directory(directory_url: HttpUrl, max_listings: int = 50):
    """Scrape leads from a business directory"""
    leads = await discovery_engine.discover_from_directory(
        str(directory_url),
        max_listings
    )

    return {
        "leads_found": len(leads),
        "source": str(directory_url),
        "leads": leads
    }


# ============================================
# LEAD MANAGEMENT ENDPOINTS
# ============================================

@router.get("/leads", tags=["Leads"])
async def list_leads(
    status: Optional[str] = None,
    min_score: Optional[float] = None,
    industry: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db)
):
    """List leads with filtering"""
    query = select(Lead).order_by(desc(Lead.lead_score), desc(Lead.created_at))

    if status:
        query = query.where(Lead.status == status)
    if min_score:
        query = query.where(Lead.lead_score >= min_score)
    if industry:
        query = query.where(Lead.industry.ilike(f"%{industry}%"))
    if search:
        query = query.where(
            Lead.company_name.ilike(f"%{search}%") |
            Lead.contact_email.ilike(f"%{search}%")
        )

    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    leads = result.scalars().all()

    # Get total count
    count_query = select(func.count(Lead.id))
    if status:
        count_query = count_query.where(Lead.status == status)
    count_result = await db.execute(count_query)
    total = count_result.scalar()

    return {
        "total": total,
        "leads": [{
            "id": l.id,
            "company_name": l.company_name,
            "website": l.website,
            "industry": l.industry,
            "contact_name": l.contact_name,
            "contact_email": l.contact_email,
            "contact_phone": l.contact_phone,
            "lead_score": l.lead_score,
            "status": l.status,
            "source": l.source,
            "created_at": l.created_at.isoformat() if l.created_at else None
        } for l in leads]
    }


@router.post("/leads", tags=["Leads"])
async def create_lead(lead_data: LeadCreate, db: AsyncSession = Depends(get_db)):
    """Create a new lead"""
    lead = Lead(
        company_name=lead_data.company_name,
        website=lead_data.website,
        industry=lead_data.industry,
        contact_name=lead_data.contact_name,
        contact_email=lead_data.contact_email,
        contact_phone=lead_data.contact_phone,
        source=lead_data.source
    )
    db.add(lead)
    await db.commit()
    await db.refresh(lead)

    return {"id": lead.id, "company_name": lead.company_name, "created": True}


@router.get("/leads/{lead_id}", tags=["Leads"])
async def get_lead(lead_id: int, db: AsyncSession = Depends(get_db)):
    """Get a specific lead by ID"""
    result = await db.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()

    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    return {
        "id": lead.id,
        "company_name": lead.company_name,
        "website": lead.website,
        "industry": lead.industry,
        "company_size": lead.company_size,
        "contact_name": lead.contact_name,
        "contact_title": lead.contact_title,
        "contact_email": lead.contact_email,
        "contact_phone": lead.contact_phone,
        "contact_linkedin": lead.contact_linkedin,
        "address": lead.address,
        "city": lead.city,
        "state": lead.state,
        "country": lead.country,
        "lead_score": lead.lead_score,
        "intent_score": lead.intent_score,
        "fit_score": lead.fit_score,
        "status": lead.status,
        "source": lead.source,
        "source_url": lead.source_url,
        "technologies": lead.technologies,
        "social_profiles": lead.social_profiles,
        "funding_info": lead.funding_info,
        "ai_summary": lead.ai_summary,
        "ai_insights": lead.ai_insights,
        "pain_points": lead.pain_points,
        "dnc_status": lead.dnc_status,
        "email_sent": lead.email_sent,
        "sms_sent": lead.sms_sent,
        "created_at": lead.created_at.isoformat() if lead.created_at else None,
        "updated_at": lead.updated_at.isoformat() if lead.updated_at else None
    }


@router.patch("/leads/{lead_id}", tags=["Leads"])
async def update_lead(lead_id: int, lead_data: LeadUpdate, db: AsyncSession = Depends(get_db)):
    """Update a lead"""
    result = await db.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()

    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    update_data = lead_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(lead, key, value)

    await db.commit()

    return {"id": lead.id, "updated": True}


@router.delete("/leads/{lead_id}", tags=["Leads"])
async def delete_lead(lead_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a lead"""
    result = await db.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()

    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    await db.delete(lead)
    await db.commit()

    return {"id": lead_id, "deleted": True}


# ============================================
# LEAD SCORING & ENRICHMENT
# ============================================

@router.post("/leads/{lead_id}/score", tags=["Scoring"])
async def score_lead(lead_id: int, db: AsyncSession = Depends(get_db)):
    """Score a lead using AI"""
    result = await db.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()

    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    # Prepare lead data for scoring
    lead_data = {
        "company_name": lead.company_name,
        "website": lead.website,
        "industry": lead.industry,
        "company_size": lead.company_size,
        "technologies": lead.technologies,
        "pain_points": lead.pain_points,
        "social_links": lead.social_profiles
    }

    # Score the lead
    score_result = await scoring_engine.score_lead(lead_data)

    # Update lead with scores
    lead.lead_score = score_result["total_score"]
    lead.fit_score = score_result["breakdown"]["fit_score"]
    lead.intent_score = score_result["breakdown"]["intent_score"]
    lead.ai_insights = score_result

    await db.commit()

    return score_result


@router.post("/leads/{lead_id}/enrich", tags=["Enrichment"])
async def enrich_lead(lead_id: int, db: AsyncSession = Depends(get_db)):
    """Enrich a lead with additional data"""
    result = await db.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()

    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    # Prepare lead data
    lead_data = {
        "company_name": lead.company_name,
        "website": lead.website,
        "industry": lead.industry
    }

    # Scrape website if available
    if lead.website:
        scraper_instance = FirecrawlScraper()
        try:
            scrape_result = await scraper_instance.scrape_single(lead.website)
            if scrape_result.get("success"):
                lead_data["raw_content"] = scrape_result.get("content", {}).get("text", "")
                if scrape_result.get("lead_info"):
                    lead_data.update(scrape_result["lead_info"])
        finally:
            await scraper_instance.close()

    # Enrich the lead
    enriched = await enrichment_service.enrich_lead(lead_data)

    # Update lead
    if enriched.get("contact_email") and not lead.contact_email:
        lead.contact_email = enriched["contact_email"]
    if enriched.get("contact_phone") and not lead.contact_phone:
        lead.contact_phone = enriched["contact_phone"]
    if enriched.get("technologies"):
        lead.technologies = enriched["technologies"]
    if enriched.get("company_size"):
        lead.company_size = enriched["company_size"]
    if enriched.get("social_links"):
        lead.social_profiles = enriched["social_links"]

    lead.ai_insights = {
        **lead.ai_insights if lead.ai_insights else {},
        "talking_points": enriched.get("talking_points", []),
        "enrichment": enriched.get("enrichment", {})
    }

    await db.commit()

    return {
        "id": lead.id,
        "enriched": True,
        "fields_added": enriched.get("enrichment", {}).get("fields_added", 0),
        "talking_points": enriched.get("talking_points", [])
    }


@router.post("/leads/bulk-score", tags=["Scoring"])
async def bulk_score_leads(lead_ids: List[int], db: AsyncSession = Depends(get_db)):
    """Score multiple leads"""
    result = await db.execute(select(Lead).where(Lead.id.in_(lead_ids)))
    leads = result.scalars().all()

    results = []
    for lead in leads:
        lead_data = {
            "company_name": lead.company_name,
            "website": lead.website,
            "industry": lead.industry,
            "company_size": lead.company_size,
            "technologies": lead.technologies
        }

        score_result = await scoring_engine.score_lead(lead_data)
        lead.lead_score = score_result["total_score"]
        lead.fit_score = score_result["breakdown"]["fit_score"]
        lead.intent_score = score_result["breakdown"]["intent_score"]

        results.append({
            "id": lead.id,
            "company_name": lead.company_name,
            "score": score_result["total_score"],
            "grade": score_result["grade"]
        })

    await db.commit()

    return {"scored": len(results), "results": results}


# ============================================
# BULK OPERATIONS
# ============================================

@router.post("/leads/bulk-import", tags=["Bulk"])
async def bulk_import_leads(request: BulkImportRequest, db: AsyncSession = Depends(get_db)):
    """Import leads in bulk"""
    imported = []

    for lead_data in request.leads:
        lead = Lead(
            company_name=lead_data.get("company_name", "Unknown"),
            website=lead_data.get("website"),
            industry=lead_data.get("industry"),
            contact_name=lead_data.get("contact_name"),
            contact_email=lead_data.get("contact_email"),
            contact_phone=lead_data.get("contact_phone"),
            source=request.source
        )
        db.add(lead)
        imported.append(lead)

    await db.commit()

    # Auto-enrich and score if requested
    results = []
    for lead in imported:
        result = {"id": lead.id, "company_name": lead.company_name}

        if request.auto_score:
            score = await scoring_engine.score_lead({
                "company_name": lead.company_name,
                "website": lead.website,
                "industry": lead.industry
            })
            lead.lead_score = score["total_score"]
            result["score"] = score["total_score"]

        results.append(result)

    await db.commit()

    return {
        "imported": len(imported),
        "results": results
    }


@router.post("/leads/export", tags=["Export"])
async def export_leads(request: ExportRequest, db: AsyncSession = Depends(get_db)):
    """Export leads to various formats"""
    import pandas as pd
    import io

    query = select(Lead)

    # Apply filters
    if request.filters:
        if request.filters.get("status"):
            query = query.where(Lead.status == request.filters["status"])
        if request.filters.get("min_score"):
            query = query.where(Lead.lead_score >= request.filters["min_score"])

    result = await db.execute(query)
    leads = result.scalars().all()

    # Convert to DataFrame
    data = []
    for lead in leads:
        row = {
            "id": lead.id,
            "company_name": lead.company_name,
            "website": lead.website,
            "industry": lead.industry,
            "contact_name": lead.contact_name,
            "contact_email": lead.contact_email,
            "contact_phone": lead.contact_phone,
            "lead_score": lead.lead_score,
            "status": lead.status,
            "source": lead.source,
            "created_at": lead.created_at.isoformat() if lead.created_at else None
        }

        # Filter fields if specified
        if request.fields:
            row = {k: v for k, v in row.items() if k in request.fields}

        data.append(row)

    df = pd.DataFrame(data)

    # Export based on format
    if request.format == "csv":
        output = io.StringIO()
        df.to_csv(output, index=False)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=leads.csv"}
        )

    elif request.format == "json":
        return df.to_dict(orient="records")

    elif request.format == "excel":
        output = io.BytesIO()
        df.to_excel(output, index=False)
        output.seek(0)
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=leads.xlsx"}
        )

    else:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {request.format}")


# ============================================
# CAMPAIGN ENDPOINTS
# ============================================

@router.get("/campaigns", tags=["Campaigns"])
async def list_campaigns(db: AsyncSession = Depends(get_db)):
    """List all campaigns"""
    result = await db.execute(
        select(Campaign).order_by(desc(Campaign.created_at))
    )
    campaigns = result.scalars().all()

    return [{
        "id": c.id,
        "name": c.name,
        "type": c.campaign_type,
        "status": c.status,
        "total_recipients": c.total_recipients,
        "sent_count": c.sent_count,
        "open_count": c.open_count,
        "created_at": c.created_at.isoformat() if c.created_at else None
    } for c in campaigns]


@router.post("/campaigns", tags=["Campaigns"])
async def create_campaign(campaign_data: CampaignCreate, db: AsyncSession = Depends(get_db)):
    """Create a new campaign"""
    campaign = Campaign(
        name=campaign_data.name,
        description=campaign_data.description,
        campaign_type=campaign_data.campaign_type,
        email_subject=campaign_data.email_subject,
        email_template=campaign_data.email_template,
        sms_template=campaign_data.sms_template,
        lead_filters=campaign_data.lead_filters
    )
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)

    return {"id": campaign.id, "name": campaign.name, "created": True}


@router.get("/campaigns/{campaign_id}", tags=["Campaigns"])
async def get_campaign(campaign_id: int, db: AsyncSession = Depends(get_db)):
    """Get campaign details"""
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id)
    )
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    return {
        "id": campaign.id,
        "name": campaign.name,
        "description": campaign.description,
        "type": campaign.campaign_type,
        "email_subject": campaign.email_subject,
        "email_template": campaign.email_template,
        "sms_template": campaign.sms_template,
        "status": campaign.status,
        "total_recipients": campaign.total_recipients,
        "sent_count": campaign.sent_count,
        "open_count": campaign.open_count,
        "click_count": campaign.click_count,
        "reply_count": campaign.reply_count,
        "lead_filters": campaign.lead_filters,
        "created_at": campaign.created_at.isoformat() if campaign.created_at else None
    }


# ============================================
# ANALYTICS ENDPOINTS
# ============================================

@router.get("/analytics/overview", tags=["Analytics"])
async def get_analytics_overview(db: AsyncSession = Depends(get_db)):
    """Get overall analytics"""
    # Total leads
    total_result = await db.execute(select(func.count(Lead.id)))
    total_leads = total_result.scalar()

    # Leads by status
    status_result = await db.execute(
        select(Lead.status, func.count(Lead.id))
        .group_by(Lead.status)
    )
    by_status = dict(status_result.all())

    # Average score
    score_result = await db.execute(
        select(func.avg(Lead.lead_score))
        .where(Lead.lead_score > 0)
    )
    avg_score = score_result.scalar() or 0

    # High quality leads (score > 70)
    high_quality_result = await db.execute(
        select(func.count(Lead.id))
        .where(Lead.lead_score >= 70)
    )
    high_quality = high_quality_result.scalar()

    # Recent leads (last 7 days)
    from datetime import timedelta
    week_ago = datetime.utcnow() - timedelta(days=7)
    recent_result = await db.execute(
        select(func.count(Lead.id))
        .where(Lead.created_at >= week_ago)
    )
    recent_leads = recent_result.scalar()

    # Top industries
    industry_result = await db.execute(
        select(Lead.industry, func.count(Lead.id))
        .where(Lead.industry.isnot(None))
        .group_by(Lead.industry)
        .order_by(desc(func.count(Lead.id)))
        .limit(5)
    )
    top_industries = dict(industry_result.all())

    return {
        "total_leads": total_leads,
        "by_status": by_status,
        "avg_score": round(avg_score, 1),
        "high_quality_leads": high_quality,
        "recent_leads": recent_leads,
        "top_industries": top_industries
    }


@router.get("/analytics/score-distribution", tags=["Analytics"])
async def get_score_distribution(db: AsyncSession = Depends(get_db)):
    """Get lead score distribution"""
    result = await db.execute(
        select(
            func.floor(Lead.lead_score / 10) * 10,
            func.count(Lead.id)
        )
        .where(Lead.lead_score > 0)
        .group_by(func.floor(Lead.lead_score / 10) * 10)
        .order_by(func.floor(Lead.lead_score / 10) * 10)
    )

    distribution = {f"{int(score)}-{int(score)+9}": count for score, count in result.all()}

    return {"distribution": distribution}


# ============================================
# HEALTH CHECK
# ============================================

@router.get("/health", tags=["System"])
async def health_check():
    """System health check"""
    return {
        "status": "healthy",
        "version": "2.0.0",
        "timestamp": datetime.utcnow().isoformat()
    }
