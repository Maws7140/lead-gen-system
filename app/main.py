"""
LeadGen Pro - Main FastAPI Application
AI-Powered Lead Generation System with Firecrawl-style Capabilities
"""

import json
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict, List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from app.api.routes import router as api_router
from app.models.database import init_db
from app.core.config import settings


# ============================================
# WebSocket Connection Manager
# ============================================

class ConnectionManager:
    """Manage WebSocket connections for real-time updates"""

    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, channel: str = "default"):
        await websocket.accept()
        if channel not in self.active_connections:
            self.active_connections[channel] = []
        self.active_connections[channel].append(websocket)

    def disconnect(self, websocket: WebSocket, channel: str = "default"):
        if channel in self.active_connections:
            self.active_connections[channel].remove(websocket)

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        await websocket.send_json(message)

    async def broadcast(self, message: dict, channel: str = "default"):
        if channel in self.active_connections:
            for connection in self.active_connections[channel]:
                try:
                    await connection.send_json(message)
                except Exception:
                    pass

    async def broadcast_all(self, message: dict):
        for channel in self.active_connections:
            await self.broadcast(message, channel)


manager = ConnectionManager()


# ============================================
# Application Lifecycle
# ============================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events"""
    # Startup
    print("Starting LeadGen Pro v2.0...")
    await init_db()
    print("Database initialized")
    yield
    # Shutdown
    print("Shutting down LeadGen Pro...")


# ============================================
# Create FastAPI Application
# ============================================

app = FastAPI(
    title="LeadGen Pro",
    description="""
    ## AI-Powered Lead Generation System

    LeadGen Pro is a comprehensive lead generation platform with Firecrawl-style
    web scraping capabilities and AI-powered data extraction.

    ### Features

    * **Intelligent Web Scraping** - Scrape single pages, crawl entire sites, or map site structure
    * **AI Data Extraction** - Extract structured data using custom schemas
    * **Lead Scoring** - AI-powered lead scoring with multiple dimensions
    * **Lead Enrichment** - Automatically enrich leads with additional data
    * **Campaign Management** - Create and manage outreach campaigns
    * **Real-time Updates** - WebSocket support for live progress updates
    * **Export & Integration** - Export to CSV, JSON, Excel

    ### Modes

    1. **Single Mode** - Scrape a single URL
    2. **Crawl Mode** - Crawl an entire website
    3. **Map Mode** - Create a sitemap of a website
    4. **Search Mode** - Search and scrape results
    5. **Discovery Mode** - AI-powered lead discovery
    """,
    version="2.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan
)


# ============================================
# Middleware
# ============================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================
# Static Files and Templates
# ============================================

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


# ============================================
# Include API Routes
# ============================================

app.include_router(api_router, prefix="/api/v1")


# ============================================
# WebSocket Endpoints
# ============================================

@app.websocket("/ws/{channel}")
async def websocket_endpoint(websocket: WebSocket, channel: str):
    """WebSocket endpoint for real-time updates"""
    await manager.connect(websocket, channel)
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            # Handle different message types
            if message.get("type") == "ping":
                await manager.send_personal_message(
                    {"type": "pong", "timestamp": datetime.utcnow().isoformat()},
                    websocket
                )
            elif message.get("type") == "subscribe":
                # Client wants to subscribe to specific events
                pass

    except WebSocketDisconnect:
        manager.disconnect(websocket, channel)


# Helper function to broadcast updates
async def broadcast_update(event_type: str, data: dict, channel: str = "default"):
    """Broadcast an update to all connected clients"""
    await manager.broadcast({
        "type": event_type,
        "data": data,
        "timestamp": datetime.utcnow().isoformat()
    }, channel)


# ============================================
# Web UI Routes
# ============================================

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard page"""
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION
    })


@app.get("/leads", response_class=HTMLResponse)
async def leads_page(request: Request):
    """Leads management page"""
    return templates.TemplateResponse("leads.html", {
        "request": request,
        "app_name": settings.APP_NAME
    })


@app.get("/scraper", response_class=HTMLResponse)
async def scraper_page(request: Request):
    """Web scraper page"""
    return templates.TemplateResponse("scraper.html", {
        "request": request,
        "app_name": settings.APP_NAME
    })


@app.get("/discovery", response_class=HTMLResponse)
async def discovery_page(request: Request):
    """Lead discovery page"""
    return templates.TemplateResponse("discovery.html", {
        "request": request,
        "app_name": settings.APP_NAME
    })


@app.get("/campaigns", response_class=HTMLResponse)
async def campaigns_page(request: Request):
    """Campaign management page"""
    return templates.TemplateResponse("campaigns.html", {
        "request": request,
        "app_name": settings.APP_NAME
    })


@app.get("/analytics", response_class=HTMLResponse)
async def analytics_page(request: Request):
    """Analytics dashboard page"""
    return templates.TemplateResponse("analytics.html", {
        "request": request,
        "app_name": settings.APP_NAME
    })


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """Settings page"""
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "app_name": settings.APP_NAME
    })


# ============================================
# Run Application
# ============================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
