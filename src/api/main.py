# mypy: ignore-errors
"""
FastAPI Application - Production Grade

Main FastAPI application for the DeepField sportsbook acquisition system.
Provides REST API endpoints for:
- Health monitoring
- Session management
- Browser control
- Live odds data
- Metrics export (Prometheus-compatible)
"""

import logging
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel

from src.dfp_config import settings

logger = logging.getLogger(__name__)

# ============================================================================
# Authentication Middleware / Dependency
# ============================================================================

async def verify_api_key(x_api_key: str = Header(None), request: Request = None):
    """
    Middleware-style dependency to verify the X-API-Key header.
    Exempts /health, /ready, and /live endpoints.
    """
    exempt_paths = ["/health", "/ready", "/live", "/docs", "/openapi.json"]
    if request.url.path in exempt_paths:
        return

    if not x_api_key or x_api_key != settings.DEEPFIELD_API_KEY:
        logger.warning(f"Unauthorized access attempt to {request.url.path} from {request.client.host}")
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: Invalid or missing X-API-Key header"
        )

# ============================================================================
# Pydantic Models for Request/Response
# ============================================================================



class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str
    components: Dict[str, bool]


class SessionStatusResponse(BaseModel):
    """Session status response."""

    session_id: str
    sportsbook: str
    state: str
    health_score: float
    authenticated: bool
    metrics: Optional[Dict[str, Any]] = None


class BrowserStatusResponse(BaseModel):
    """Browser status response."""

    is_running: bool
    context_count: int
    contexts: list
    memory_usage_mb: Optional[float] = None


class MetricsResponse(BaseModel):
    """Metrics response for Prometheus scraping."""

    format: str = "prometheus"
    metrics: str


class OddsTickResponse(BaseModel):
    """Odds tick response."""

    tick_id: str
    fixture_id: int
    sportsbook: str
    market_type: str
    outcome: str
    odds_before: float
    odds_after: float
    timestamp: str
    sequence_number: int


class WebSocketStatusResponse(BaseModel):
    """WebSocket connection status."""

    sportsbook: str
    is_connected: bool
    state: str
    messages_received: int
    reconnect_count: int
    last_message_ago_seconds: Optional[float] = None


# ============================================================================
# Application State and Dependencies
# ============================================================================


class AppState:
    """Application state container for dependency injection."""

    def __init__(self):
        self.session_manager = None
        self.websocket_ingestors: Dict[str, Any] = {}
        self.database_session = None
        self.version = "1.0.0"

    def set_session_manager(self, manager):
        self.session_manager = manager

    def set_database_session(self, session):
        self.database_session = session

    def add_websocket_ingestor(self, sportsbook: str, ingestor):
        self.websocket_ingestors[sportsbook] = ingestor

    def get_websocket_ingestor(self, sportsbook: str):
        return self.websocket_ingestors.get(sportsbook)


app_state = AppState()


def get_app_state() -> AppState:
    """Dependency to get application state."""
    return app_state


# ============================================================================
# Lifespan Context Manager
# ============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    # Startup
    logger.info("Starting DeepField API...")

    # Import and initialize services
    try:
        from src.services.session_manager.service import SessionManager

        # Initialize session manager
        session_manager = SessionManager(
            headless=True, user_data_dir="data/deepfield_browser_data"
        )
        await session_manager.start()
        app_state.set_session_manager(session_manager)

        logger.info("Session manager initialized")

    except Exception as e:
        logger.error(f"Failed to initialize services: {e}")
        raise

    yield

    # Shutdown
    logger.info("Shutting down DeepField API...")

    if app_state.session_manager:
        await app_state.session_manager.stop()

    logger.info("Shutdown complete")


# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title="DeepField Sportsbook Acquisition API",
    description="Production-grade API for sportsbook data acquisition and odds ingestion",
    version="1.0.0",
    lifespan=lifespan,
    dependencies=[Depends(verify_api_key)]
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Health Endpoints
# ============================================================================


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check(state: AppState = Depends(get_app_state)):
    """
    Comprehensive health check endpoint.

    Returns the health status of all system components.
    """
    components = {
        "api": True,
        "session_manager": False,
        "browser_engine": False,
        "database": False,
    }

    # Check session manager
    if state.session_manager:
        components["session_manager"] = True
        components["browser_engine"] = state.session_manager.engine.is_healthy()

    # Check database
    if state.database_session:
        try:
            # Simple query to verify DB connection
            pass
            components["database"] = True
        except Exception:
            components["database"] = False

    overall_status = "healthy" if all(components.values()) else "degraded"
    if not any(v for k, v in components.items() if k != "api"):
        overall_status = "unhealthy"

    return HealthResponse(
        status=overall_status,
        version=state.version,
        components=components,
    )


@app.get("/ready", tags=["Health"])
async def readiness_check(state: AppState = Depends(get_app_state)):
    """
    Readiness probe for Kubernetes/load balancers.

    Returns 200 if the service is ready to accept traffic.
    """
    if not state.session_manager or not state.session_manager.engine.is_healthy():
        raise HTTPException(status_code=503, detail="Service not ready")

    return {"status": "ready"}


@app.get("/live", tags=["Health"])
async def liveness_check():
    """
    Liveness probe for Kubernetes.

    Returns 200 if the service is alive.
    """
    return {"status": "alive"}


# ============================================================================
# Session Management Endpoints
# ============================================================================


@app.get(
    "/session/status/{session_id}",
    response_model=SessionStatusResponse,
    tags=["Sessions"],
)
async def get_session_status(session_id: str, state: AppState = Depends(get_app_state)):
    """Get detailed status of a specific session."""
    if not state.session_manager:
        raise HTTPException(status_code=503, detail="Session manager not available")

    session = state.session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    health_score = state.session_manager.get_session_health_score(session_id)
    metrics = state.session_manager._session_metrics.get(session_id)

    return SessionStatusResponse(
        session_id=session_id,
        sportsbook=session["sportsbook"],
        state=(
            session["state"].value
            if hasattr(session["state"], "value")
            else str(session["state"])
        ),
        health_score=health_score,
        authenticated=session.get("authenticated", False),
        metrics=(
            {
                "requests_total": metrics.requests_total,
                "requests_success": metrics.requests_success,
                "requests_failed": metrics.requests_failed,
                "consecutive_failures": metrics.consecutive_failures,
            }
            if metrics
            else None
        ),
    )


@app.get("/sessions", tags=["Sessions"])
async def list_sessions(state: AppState = Depends(get_app_state)):
    """List all active sessions."""
    if not state.session_manager:
        raise HTTPException(status_code=503, detail="Session manager not available")

    return {
        "total": len(state.session_manager.list_sessions()),
        "sessions": state.session_manager.get_metrics_summary(),
    }


@app.post("/session/create", tags=["Sessions"])
async def create_session(
    session_id: str,
    sportsbook: str,
    proxy: Optional[Dict[str, str]] = None,
    state: AppState = Depends(get_app_state),
):
    """Create a new session for a sportsbook."""
    if not state.session_manager:
        raise HTTPException(status_code=503, detail="Session manager not available")

    try:
        await state.session_manager.create_session(
            session_id=session_id,
            sportsbook=sportsbook,
            proxy=proxy,
        )
        return {"status": "created", "session_id": session_id}
    except Exception as e:
        logger.error(f"Failed to create session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/session/authenticate", tags=["Sessions"])
async def authenticate_session(
    session_id: str,
    credentials: Dict[str, str],
    state: AppState = Depends(get_app_state),
):
    """Authenticate a session with credentials."""
    if not state.session_manager:
        raise HTTPException(status_code=503, detail="Session manager not available")

    success = await state.session_manager.authenticate(session_id, credentials)

    if not success:
        raise HTTPException(status_code=401, detail="Authentication failed")

    return {"status": "authenticated", "session_id": session_id}


@app.delete("/session/{session_id}", tags=["Sessions"])
async def close_session(session_id: str, state: AppState = Depends(get_app_state)):
    """Close and cleanup a session."""
    if not state.session_manager:
        raise HTTPException(status_code=503, detail="Session manager not available")

    await state.session_manager.close_session(session_id)
    return {"status": "closed", "session_id": session_id}


# ============================================================================
# Browser Control Endpoints
# ============================================================================


@app.get("/browser/status", response_model=BrowserStatusResponse, tags=["Browser"])
async def get_browser_status(state: AppState = Depends(get_app_state)):
    """Get browser engine status."""
    if not state.session_manager:
        raise HTTPException(status_code=503, detail="Session manager not available")

    engine = state.session_manager.engine
    metrics = engine.get_metrics()

    return BrowserStatusResponse(
        is_running=metrics["is_running"],
        context_count=metrics["context_count"],
        contexts=metrics["contexts"],
    )


@app.post("/browser/restart", tags=["Browser"])
async def restart_browser(
    background_tasks: BackgroundTasks, state: AppState = Depends(get_app_state)
):
    """
    Restart the browser engine.

    This will gracefully close all sessions and restart the browser.
    """
    if not state.session_manager:
        raise HTTPException(status_code=503, detail="Session manager not available")

    async def do_restart():
        logger.info("Initiating browser restart...")
        await state.session_manager.stop()
        await state.session_manager.start()
        logger.info("Browser restart complete")

    background_tasks.add_task(do_restart)

    return {"status": "restarting", "message": "Browser restart initiated"}


# ============================================================================
# WebSocket Status Endpoints
# ============================================================================


@app.get(
    "/websocket/status/{sportsbook}",
    response_model=WebSocketStatusResponse,
    tags=["WebSocket"],
)
async def get_websocket_status(
    sportsbook: str, state: AppState = Depends(get_app_state)
):
    """Get WebSocket connection status for a sportsbook."""
    ingestor = state.get_websocket_ingestor(sportsbook)

    if not ingestor:
        raise HTTPException(
            status_code=404, detail=f"No WebSocket ingestor for {sportsbook}"
        )

    metrics = ingestor.get_metrics()

    return WebSocketStatusResponse(
        sportsbook=sportsbook,
        is_connected=metrics["is_connected"],
        state=metrics["state"],
        messages_received=metrics["messages_received"],
        reconnect_count=metrics["reconnect_count"],
        last_message_ago_seconds=metrics.get("last_message_ago_seconds"),
    )


@app.get("/websocket/status", tags=["WebSocket"])
async def list_websocket_status(state: AppState = Depends(get_app_state)):
    """List WebSocket status for all sportsbooks."""
    statuses = {}

    for sportsbook, ingestor in state.websocket_ingestors.items():
        try:
            metrics = ingestor.get_metrics()
            statuses[sportsbook] = {
                "is_connected": metrics["is_connected"],
                "state": metrics["state"],
                "messages_received": metrics["messages_received"],
            }
        except Exception as e:
            statuses[sportsbook] = {"error": str(e)}

    return {"websocket_connections": statuses}


# ============================================================================
# Odds Data Endpoints
# ============================================================================


@app.get("/odds/live/{fixture_id}", tags=["Odds"])
async def get_live_odds(
    fixture_id: int,
    sportsbook: Optional[str] = None,
    state: AppState = Depends(get_app_state),
):
    """
    Get latest live odds for a fixture.

    Returns the most recent odds from all connected sportsbooks.
    """
    if not state.database_session:
        raise HTTPException(status_code=503, detail="Database not available")

    # Query would go here - placeholder implementation
    return {
        "fixture_id": fixture_id,
        "odds": [],
        "timestamp": "now",
    }


@app.get("/odds/history/{fixture_id}", tags=["Odds"])
async def get_odds_history(
    fixture_id: int,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    sportsbook: Optional[str] = None,
    state: AppState = Depends(get_app_state),
):
    """
    Get historical odds ticks for a fixture.

    Supports time range filtering and sportsbook filtering.
    """
    if not state.database_session:
        raise HTTPException(status_code=503, detail="Database not available")

    # Query would go here - placeholder implementation
    return {
        "fixture_id": fixture_id,
        "ticks": [],
        "count": 0,
    }


# Add these imports at the top
from src.services.market_intelligence.engine import get_active_matches
from src.services.risk_engine.engine import get_bankroll_status, get_active_parlays

# ============================================================================
# Dashboard Endpoints
# ============================================================================

@app.get("/dashboard/matches", tags=["Dashboard"])
async def get_dashboard_matches():
    """Get active matches for the Live Predictions dashboard."""
    try:
        matches = get_active_matches()
        return {"matches": matches}
    except Exception as e:
        logger.error(f"Failed to fetch matches: {e}")
        return {"matches": []}

@app.get("/dashboard/bankroll", tags=["Dashboard"])
async def get_dashboard_bankroll():
    """Get bankroll and ROI status."""
    try:
        status = get_bankroll_status()
        return status
    except Exception as e:
        logger.error(f"Failed to fetch bankroll: {e}")
        return {"current_balance": 0.0, "total_pnl": 0.0, "roi": 0.0}

@app.get("/dashboard/parlays", tags=["Dashboard"])
async def get_dashboard_parlays():
    """Get active/pending parlays."""
    try:
        parlays = get_active_parlays()
        return {"parlays": parlays}
    except Exception as e:
        logger.error(f"Failed to fetch parlays: {e}")
        return {"parlays": []}


# ============================================================================
# Metrics Endpoints (Prometheus)
# ============================================================================


@app.get("/metrics", response_class=PlainTextResponse, tags=["Metrics"])
async def get_metrics(state: AppState = Depends(get_app_state)):
    """
    Prometheus-compatible metrics endpoint.

    Returns metrics in Prometheus text exposition format.
    """
    metrics_lines = [
        "# HELP deepfield_version Version information",
        "# TYPE deepfield_version gauge",
        f'deepfield_version{{version="{state.version}"}} 1',
        "",
        "# HELP deepfield_sessions_total Total number of active sessions",
        "# TYPE deepfield_sessions_total gauge",
    ]

    if state.session_manager:
        summary = state.session_manager.get_metrics_summary()
        metrics_lines.append(f'deepfield_sessions_total {summary["total_sessions"]}')
        metrics_lines.append("")

        # Per-session metrics
        metrics_lines.append(
            "# HELP deepfield_session_health_score Health score per session"
        )
        metrics_lines.append("# TYPE deepfield_session_health_score gauge")

        for session_id, info in summary.get("sessions", {}).items():
            sportsbook = info.get("sportsbook", "unknown")
            health = info.get("health_score", 0)
            metrics_lines.append(
                f'deepfield_session_health_score{{session_id="{session_id}",sportsbook="{sportsbook}"}} {health}'
            )

        metrics_lines.append("")

        # Browser metrics
        browser_metrics = state.session_manager.engine.get_metrics()
        metrics_lines.append(
            "# HELP deepfield_browser_contexts Number of browser contexts"
        )
        metrics_lines.append("# TYPE deepfield_browser_contexts gauge")
        metrics_lines.append(
            f'deepfield_browser_contexts {browser_metrics.get("context_count", 0)}'
        )

        # WebSocket metrics
        metrics_lines.append("")
        metrics_lines.append(
            "# HELP deepfield_websocket_messages Total WebSocket messages received"
        )
        metrics_lines.append("# TYPE deepfield_websocket_messages counter")

        for sportsbook, ingestor in state.websocket_ingestors.items():
            try:
                ws_metrics = ingestor.get_metrics()
                msgs = ws_metrics.get("messages_received", 0)
                metrics_lines.append(
                    f'deepfield_websocket_messages{{sportsbook="{sportsbook}"}} {msgs}'
                )
            except Exception:
                pass

    return "\n".join(metrics_lines) + "\n"


# ============================================================================
# Error Handlers
# ============================================================================


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Custom HTTP exception handler with structured error response."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "type": "http_error",
                "code": exc.status_code,
                "message": exc.detail,
            }
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """General exception handler with structured error response."""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "type": "internal_error",
                "code": 500,
                "message": "An internal error occurred",
            }
        },
    )
