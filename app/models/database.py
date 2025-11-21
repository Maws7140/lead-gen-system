"""
Database models and connection management
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, Text, JSON, ForeignKey, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, relationship
import enum

from app.core.config import settings

# Create async engine
engine = create_async_engine(settings.DATABASE_URL, echo=settings.DEBUG)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()


class LeadStatus(str, enum.Enum):
    NEW = "new"
    ENRICHED = "enriched"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    CONVERTED = "converted"
    LOST = "lost"


class ScrapeMode(str, enum.Enum):
    SINGLE = "single"
    CRAWL = "crawl"
    MAP = "map"
    SEARCH = "search"


class Lead(Base):
    """Lead model for storing potential customers"""
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True)

    # Basic info
    company_name = Column(String(255), index=True)
    website = Column(String(500))
    industry = Column(String(100))
    company_size = Column(String(50))

    # Contact info
    contact_name = Column(String(255))
    contact_title = Column(String(255))
    contact_email = Column(String(255), index=True)
    contact_phone = Column(String(50))
    contact_linkedin = Column(String(500))

    # Location
    address = Column(String(500))
    city = Column(String(100))
    state = Column(String(100))
    country = Column(String(100))

    # Lead scoring
    lead_score = Column(Float, default=0.0)
    intent_score = Column(Float, default=0.0)
    fit_score = Column(Float, default=0.0)

    # Status and tracking
    status = Column(String(50), default=LeadStatus.NEW.value)
    source = Column(String(100))
    source_url = Column(String(500))

    # Enrichment data
    technologies = Column(JSON, default=list)
    social_profiles = Column(JSON, default=dict)
    funding_info = Column(JSON, default=dict)

    # AI-extracted data
    ai_summary = Column(Text)
    ai_insights = Column(JSON, default=dict)
    pain_points = Column(JSON, default=list)

    # Campaign tracking
    dnc_status = Column(Boolean, default=False)
    email_sent = Column(Boolean, default=False)
    sms_sent = Column(Boolean, default=False)
    last_contacted = Column(DateTime)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    scrape_jobs = relationship("ScrapeJob", back_populates="lead")
    activities = relationship("Activity", back_populates="lead")


class ScrapeJob(Base):
    """Track scraping jobs and their results"""
    __tablename__ = "scrape_jobs"

    id = Column(Integer, primary_key=True, index=True)

    # Job info
    job_id = Column(String(100), unique=True, index=True)
    mode = Column(String(50), default=ScrapeMode.SINGLE.value)
    url = Column(String(500))

    # Configuration
    config = Column(JSON, default=dict)
    extraction_schema = Column(JSON)

    # Status
    status = Column(String(50), default="pending")  # pending, running, completed, failed
    progress = Column(Float, default=0.0)
    pages_scraped = Column(Integer, default=0)
    total_pages = Column(Integer, default=0)

    # Results
    raw_content = Column(Text)
    extracted_data = Column(JSON)
    error_message = Column(Text)

    # Performance
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    duration_seconds = Column(Float)

    # Relationships
    lead_id = Column(Integer, ForeignKey("leads.id"))
    lead = relationship("Lead", back_populates="scrape_jobs")

    created_at = Column(DateTime, default=datetime.utcnow)


class Activity(Base):
    """Track all activities related to leads"""
    __tablename__ = "activities"

    id = Column(Integer, primary_key=True, index=True)

    lead_id = Column(Integer, ForeignKey("leads.id"))
    lead = relationship("Lead", back_populates="activities")

    activity_type = Column(String(50))  # email, sms, call, note, status_change
    description = Column(Text)
    metadata = Column(JSON, default=dict)

    created_at = Column(DateTime, default=datetime.utcnow)


class Campaign(Base):
    """Email and SMS campaign management"""
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String(255))
    description = Column(Text)
    campaign_type = Column(String(50))  # email, sms, multi-channel

    # Templates
    email_subject = Column(String(500))
    email_template = Column(Text)
    sms_template = Column(Text)

    # Scheduling
    status = Column(String(50), default="draft")  # draft, scheduled, running, completed, paused
    scheduled_at = Column(DateTime)

    # Stats
    total_recipients = Column(Integer, default=0)
    sent_count = Column(Integer, default=0)
    open_count = Column(Integer, default=0)
    click_count = Column(Integer, default=0)
    reply_count = Column(Integer, default=0)

    # Filters
    lead_filters = Column(JSON, default=dict)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SearchQuery(Base):
    """Store search queries for lead discovery"""
    __tablename__ = "search_queries"

    id = Column(Integer, primary_key=True, index=True)

    query = Column(String(500))
    filters = Column(JSON, default=dict)
    results_count = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)


class APIKey(Base):
    """API key management for external access"""
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)

    key_hash = Column(String(255), unique=True, index=True)
    name = Column(String(100))

    # Permissions
    permissions = Column(JSON, default=list)
    rate_limit = Column(Integer, default=1000)  # requests per hour

    # Usage
    requests_count = Column(Integer, default=0)
    last_used = Column(DateTime)

    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime)

    created_at = Column(DateTime, default=datetime.utcnow)


async def init_db():
    """Initialize database tables"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    """Get database session"""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
