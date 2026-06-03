# DeepField Sportsbook Acquisition System - Production Guide

## Overview

This is a production-grade sportsbook data acquisition system that continuously ingests live odds data from multiple sportsbooks using browser automation with Playwright.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     DeepField Orchestrator                       │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────────┐  ┌──────────────────┐  ┌───────────────┐ │
│  │ Session Manager  │  │ WebSocket        │  │ FastAPI       │ │
│  │ + Browser Engine │  │ Ingestors        │  │ API Server    │ │
│  │                  │  │                  │  │               │ │
│  │ - Auth handling  │  │ - bet365         │  │ - /health     │ │
│  │ - Rate limiting  │  │ - pinnacle       │  │ - /metrics    │ │
│  │ - Circuit breaker│  │ - betfair        │  │ - /sessions   │ │
│  │ - Health scoring │  │                  │  │ - /odds/*     │ │
│  └──────────────────┘  └──────────────────┘  └───────────────┘ │
│                              │                                   │
│                              ▼                                   │
│                    ┌──────────────────┐                         │
│                    │ PostgreSQL DB    │                         │
│                    │ + TimescaleDB    │                         │
│                    │                  │                         │
│                    │ - odds_ticks     │                         │
│                    │ - line_movements │                         │
│                    │ - session_logs   │                         │
│                    └──────────────────┘                         │
└─────────────────────────────────────────────────────────────────┘
```

## Key Features

### 1. Session Stabilization
- **Persistent Chromium profiles** with state preservation
- **Advanced stealth fingerprinting** (navigator spoofing, webdriver removal, canvas masking)
- **Automatic session restoration** from persisted cookies and localStorage
- **Session expiration detection** and automatic re-authentication
- **Exponential backoff retry** logic for failed requests

### 2. Browser Hardening
- Multiple realistic browser fingerprints (Windows, Mac, Linux)
- Navigator property spoofing (webdriver, platform, vendor, languages)
- Canvas/WebGL fingerprint randomization
- Realistic viewport and timezone configuration
- Stealth script injection on every context

### 3. Network Interception
- Request/response interception via `page.on("request")` and `page.on("response")`
- WebSocket frame monitoring and decoding
- Automatic API endpoint discovery
- Auth header and token extraction

### 4. Browser-Based Fetching
- ALL API calls execute through browser context using `page.evaluate(async () => fetch(...))`
- Maintains authenticated sessions automatically
- No static tokens - browser is authentication authority

### 5. WebSocket Ingestion
- Live WebSocket connection management
- Automatic reconnection with exponential backoff
- Stream staleness detection (30-second threshold)
- Market movement tracking
- Immutable odds tick storage

### 6. Immutable Odds Storage
- Every odds change recorded as immutable tick
- Sequence numbering per market/outcome
- Support for CLV (Closing Line Value) analysis
- TimescaleDB-compatible design patterns

### 7. Session Health System
- Health scoring based on:
  - Success rate (40% weight)
  - Consecutive failures (30% weight)
  - Response latency (20% weight)
  - Session age (10% weight)
- Automatic unhealthy session replacement

### 8. Auto Recovery
- Browser crash recovery
- WebSocket auto-reconnect
- Session expiration handling
- 406/401/403 error recovery
- Circuit breaker pattern for failing sportsbooks

### 9. Observability
- Structured JSON logging
- Prometheus-compatible metrics endpoint (`/metrics`)
- Grafana-ready metrics:
  - `deepfield_sessions_total`
  - `deepfield_session_health_score`
  - `deepfield_browser_contexts`
  - `deepfield_websocket_messages`

### 10. Production Reliability
- Circuit breakers per sportsbook
- Rate limiting (60 requests/minute/session)
- Request pacing
- Retry queues
- Anti-ban cooldowns
- Service watchdogs

## Quick Start

### Prerequisites
```bash
pip install sqlalchemy fastapi playwright pydantic uvicorn
playwright install chromium
```

### Run the Orchestrator
```bash
python src/orchestrator.py
```

### Run the API Server
```bash
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

## API Endpoints

### Health
- `GET /health` - Comprehensive health check
- `GET /ready` - Readiness probe (Kubernetes)
- `GET /live` - Liveness probe (Kubernetes)

### Sessions
- `GET /sessions` - List all active sessions
- `GET /session/status/{session_id}` - Get session details
- `POST /session/create` - Create new session
- `POST /session/authenticate` - Authenticate session
- `DELETE /session/{session_id}` - Close session

### Browser
- `GET /browser/status` - Get browser engine status
- `POST /browser/restart` - Restart browser (graceful)

### WebSocket
- `GET /websocket/status` - All WebSocket connections
- `GET /websocket/status/{sportsbook}` - Specific sportsbook

### Odds
- `GET /odds/live/{fixture_id}` - Latest odds
- `GET /odds/history/{fixture_id}` - Historical ticks
- `GET /markets/active` - Active markets

### Metrics
- `GET /metrics` - Prometheus-compatible metrics

## Database Schema

### Core Tables
- `fixtures` - Match/fixture information
- `odds_ticks` - Immutable odds changes (time-series)
- `odds_snapshots` - Periodic full snapshots
- `line_movements` - Aggregated movement events
- `websocket_events` - WebSocket connection logs
- `session_logs` - Session lifecycle events
- `browser_health` - Browser resource metrics
- `ingestion_metrics` - Aggregated ingestion stats

### TimescaleDB Setup (Optional)
```sql
-- Convert odds_ticks to hypertable
SELECT create_hypertable('odds_ticks', 'timestamp');

-- Add compression
ALTER TABLE odds_ticks SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'fixture_id,sportsbook'
);

-- Add retention policy (keep 90 days)
SELECT add_retention_policy('odds_ticks', INTERVAL '90 days');
```

## Configuration

### Environment Variables
```bash
# Browser settings
HEADLESS=true
USER_DATA_DIR=/tmp/deepfield_browser_data

# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/deepfield

# Sportsbooks
SPORTSBOOKS=bet365,pinnacle,betfair

# Rate limiting
MAX_REQUESTS_PER_MINUTE=60
MAX_CONCURRENT_SESSIONS=5

# Health checks
HEALTH_CHECK_INTERVAL=30
METRICS_INTERVAL=60
```

## Monitoring

### Prometheus Metrics
```prometheus
# Total active sessions
deepfield_sessions_total

# Per-session health score (0.0-1.0)
deepfield_session_health_score{session_id="...",sportsbook="..."}

# Browser context count
deepfield_browser_contexts

# WebSocket messages per sportsbook
deepfield_websocket_messages{sportsbook="..."}
```

### Grafana Dashboard
Import the provided dashboard JSON or create panels for:
- Session health over time
- WebSocket uptime percentage
- Odds ingestion rate (ticks/second)
- Error rates by sportsbook
- Browser memory usage

## Troubleshooting

### 406 Not Acceptable Errors
- Ensure browser fingerprints are rotated
- Check that stealth scripts are injected
- Verify headers match real browser behavior

### Session Expiration
- Check `session_logs` table for expiration events
- Verify auto-reauthentication is working
- Review circuit breaker status

### WebSocket Disconnections
- Check `websocket_events` for disconnect reasons
- Monitor `last_message_ago_seconds` metric
- Verify network connectivity

### High Memory Usage
- Monitor `browser_health` table
- Consider reducing `MAX_CONCURRENT_SESSIONS`
- Enable browser context cleanup on idle

## Production Deployment

### Docker Compose
```yaml
version: '3.8'
services:
  deepfield:
    build: .
    environment:
      - DATABASE_URL=postgresql://postgres:postgres@db:5432/deepfield
    depends_on:
      - db
      - redis
    
  db:
    image: timescale/timescaledb:latest-pg15
    volumes:
      - postgres_data:/var/lib/postgresql/data
    
  redis:
    image: redis:7-alpine
    
  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    
  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
```

### Kubernetes
See `k8s/` directory for:
- Deployment manifests
- Service definitions
- ConfigMaps
- Secrets templates
- HPA configuration

## Security Considerations

1. **Credentials**: Store sportsbook credentials in secrets manager
2. **Proxy rotation**: Configure proxies per session for IP diversity
3. **Rate limiting**: Respect sportsbook rate limits to avoid bans
4. **Data encryption**: Encrypt database at rest
5. **Network isolation**: Run in isolated VPC/network

## License

Proprietary - Internal use only
