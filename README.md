# LeadGen Pro v2.0

<p align="center">
  <img src="https://img.shields.io/badge/version-2.0.0-blue.svg" alt="Version">
  <img src="https://img.shields.io/badge/python-3.9+-green.svg" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-orange.svg" alt="License">
</p>

**LeadGen Pro** is a powerful, AI-driven lead generation system with Firecrawl-style web scraping capabilities. Built for businesses and agencies that need to discover, enrich, score, and manage leads at scale.

## Features

### Core Capabilities

- **Firecrawl-Style Web Scraping**
  - Single page scraping with AI extraction
  - Full site crawling with link discovery
  - Site mapping and structure analysis
  - Search-based lead discovery

- **AI-Powered Lead Intelligence**
  - Automatic lead data extraction using GPT-4
  - Multi-dimensional lead scoring (Fit, Intent, Engagement)
  - ICP (Ideal Customer Profile) matching
  - Personalized talking points generation

- **Lead Enrichment**
  - Email and phone extraction
  - Technology stack detection
  - Company size estimation
  - Social profile discovery

- **Campaign Management**
  - Email campaign templates
  - SMS outreach templates
  - Variable personalization
  - Campaign analytics

- **Modern Web Interface**
  - Real-time dashboard with analytics
  - Lead management with bulk operations
  - WebSocket-powered live updates
  - Dark/Light mode support
  - Responsive design

### Operation Modes

1. **Single Mode** - Scrape individual URLs with custom extraction schemas
2. **Crawl Mode** - Crawl entire websites, following links within the domain
3. **Map Mode** - Create comprehensive sitemaps showing site structure
4. **Search Mode** - Search the web and scrape results
5. **Discovery Mode** - Find leads by industry and location

## Quick Start

### Prerequisites

- Python 3.9+
- OpenAI API key
- (Optional) Airtable API key

### Installation

1. Clone the repository:
```bash
git clone https://github.com/your-repo/lead-gen-system.git
cd lead-gen-system
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create your environment file:
```bash
cp env_template.txt .env
```

5. Add your API keys to `.env`:
```
OPENAI_API_KEY=sk-your-key-here
AIRTABLE_API_KEY=your-key-here  # Optional
AIRTABLE_BASE_ID=your-base-id   # Optional
```

### Running the Application

```bash
python run.py
```

Or directly with uvicorn:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Access the application:
- **Dashboard**: http://localhost:8000
- **API Docs**: http://localhost:8000/api/docs
- **ReDoc**: http://localhost:8000/api/redoc

## API Usage

### Scraping a Single Page

```bash
curl -X POST "http://localhost:8000/api/v1/scrape" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com",
    "mode": "single",
    "extraction_schema": {
      "company_name": "string",
      "contact_email": "string"
    }
  }'
```

### Crawling a Website

```bash
curl -X POST "http://localhost:8000/api/v1/scrape" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com",
    "mode": "crawl",
    "max_pages": 50
  }'
```

### Discovering Leads

```bash
curl -X POST "http://localhost:8000/api/v1/discover" \
  -H "Content-Type: application/json" \
  -d '{
    "industry": "SaaS",
    "location": "San Francisco",
    "num_leads": 20
  }'
```

### Scoring a Lead

```bash
curl -X POST "http://localhost:8000/api/v1/leads/1/score"
```

### Enriching a Lead

```bash
curl -X POST "http://localhost:8000/api/v1/leads/1/enrich"
```

### Exporting Leads

```bash
curl -X POST "http://localhost:8000/api/v1/leads/export" \
  -H "Content-Type: application/json" \
  -d '{
    "format": "csv"
  }'
```

## Project Structure

```
lead-gen-system/
├── app/
│   ├── api/
│   │   └── routes.py          # API endpoints
│   ├── core/
│   │   └── config.py          # Configuration
│   ├── models/
│   │   └── database.py        # SQLAlchemy models
│   ├── services/
│   │   ├── scraper.py         # Firecrawl-style scraper
│   │   └── lead_scoring.py    # AI scoring engine
│   ├── static/                # Static assets
│   ├── templates/             # Jinja2 templates
│   └── main.py                # FastAPI application
├── data/                      # Sample documents
├── src/                       # Legacy pipeline (v1)
├── requirements.txt           # Python dependencies
├── run.py                     # Startup script
└── README.md
```

## Lead Scoring

LeadGen Pro uses a multi-dimensional scoring system:

| Dimension | Weight | Description |
|-----------|--------|-------------|
| Fit Score | 35% | How well the lead matches your ICP |
| Intent Score | 30% | Buying intent signals detected |
| Engagement Score | 20% | Website and social engagement |
| Data Quality | 15% | Completeness of lead data |

### Score Grades

- **A+ (90-100)**: Hot lead - Contact immediately
- **A (80-89)**: High priority - Prioritize outreach
- **B (70-79)**: Warm lead - Add to nurture sequence
- **C (60-69)**: Moderate - Research further
- **D (50-59)**: Cool lead - Monitor
- **F (<50)**: Low priority - Deprioritize

## Technologies

- **Backend**: FastAPI, SQLAlchemy, Pydantic
- **Frontend**: Tailwind CSS, Alpine.js, Chart.js
- **AI/ML**: OpenAI GPT-4, Custom scoring algorithms
- **Scraping**: httpx, BeautifulSoup, lxml
- **Database**: SQLite (upgradable to PostgreSQL)

## Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `OPENAI_API_KEY` | OpenAI API key for GPT-4 | Yes |
| `AIRTABLE_API_KEY` | Airtable API key | No |
| `AIRTABLE_BASE_ID` | Airtable base ID | No |
| `DATABASE_URL` | Database connection string | No |
| `SECRET_KEY` | Application secret key | No |
| `LLM_MODEL` | GPT model to use | No |

### Ideal Customer Profile

Configure your ICP in the Settings page or via the API:

```python
{
    "company_sizes": ["11-50", "51-200", "201-500"],
    "industries": ["technology", "software", "saas"],
    "technologies": ["react", "python", "aws"],
    "locations": ["united states", "canada"]
}
```

## Integrations

- **Airtable**: Sync leads to Airtable
- **HubSpot**: (Coming soon)
- **Salesforce**: (Coming soon)
- **Zapier**: (Coming soon)

## Export Formats

- CSV
- JSON
- Excel (.xlsx)

## Best Practices

1. **Rate Limiting**: Respect website rate limits (1 request/second default)
2. **Robots.txt**: Check robots.txt before aggressive crawling
3. **Data Quality**: Always verify enriched data
4. **GDPR**: Ensure compliance with data protection laws
5. **DNC Lists**: Check Do-Not-Call lists before outreach

## Legacy Pipeline (v1)

The original document processing pipeline is still available in the `src/` directory:

```bash
# Process documents
python src/main.py

# Run campaign triggers
python src/campaign_trigger.py
```

## Contributing

Contributions are welcome! Please read our contributing guidelines before submitting PRs.

## License

MIT License - see LICENSE file for details.

## Support

- Documentation: See `/api/docs` for API documentation
- Issues: Report bugs on GitHub Issues
- Feature Requests: Submit via GitHub Issues

---

Built with care for lead generation professionals
