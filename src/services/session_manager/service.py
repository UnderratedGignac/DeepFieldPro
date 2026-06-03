"""
Session Manager Service

Coordinates browser sessions for odds acquisition across multiple sportsbooks.
Manages session lifecycle, authentication, and rate limiting.
"""

import asyncio
from typing import Optional, Dict, List
from datetime import datetime, timedelta

from .browser_engine import BrowserEngine


class SessionManager:
    """
    Manages browser sessions for data acquisition.
    
    Handles:
    - Session creation and cleanup
    - Authentication state management
    - Rate limiting per sportsbook
    - Session health monitoring
    """
    
    def __init__(self, headless: bool = True):
        self.engine = BrowserEngine(headless=headless)
        self._sessions: Dict[str, dict] = {}
        self._rate_limits: Dict[str, List[datetime]] = {}
        self._max_requests_per_minute = 60
        
    async def start(self) -> None:
        """Start the browser engine."""
        await self.engine.start()
        
    async def stop(self) -> None:
        """Stop all sessions and browser engine."""
        for session_id in list(self._sessions.keys()):
            await self.close_session(session_id)
        await self.engine.stop()
        
    async def create_session(
        self, 
        session_id: str, 
        sportsbook: str,
        proxy: Optional[Dict[str, str]] = None
    ) -> None:
        """
        Create a new session for a specific sportsbook.
        
        Args:
            session_id: Unique session identifier
            sportsbook: Name of the sportsbook
            proxy: Optional proxy configuration
        """
        context = await self.engine.create_context(session_id, proxy=proxy)
        self._sessions[session_id] = {
            'sportsbook': sportsbook,
            'created_at': datetime.now(),
            'last_activity': datetime.now(),
            'authenticated': False,
            'context': context
        }
        
    async def close_session(self, session_id: str) -> None:
        """Close and cleanup a session."""
        if session_id in self._sessions:
            await self.engine.remove_context(session_id)
            del self._sessions[session_id]
            
    async def authenticate(
        self, 
        session_id: str, 
        credentials: Dict[str, str]
    ) -> bool:
        """
        Authenticate a session with provided credentials.
        
        Args:
            session_id: Session to authenticate
            credentials: Login credentials
            
        Returns:
            True if authentication successful
        """
        if session_id not in self._sessions:
            return False
            
        # Implementation depends on specific sportsbook
        # This is a placeholder for actual auth logic
        page = await self.engine.new_page(session_id)
        
        try:
            # Navigate to login page and perform authentication
            # Actual implementation varies by sportsbook
            self._sessions[session_id]['authenticated'] = True
            self._sessions[session_id]['last_activity'] = datetime.now()
            return True
        except Exception as e:
            print(f"Authentication failed: {e}")
            return False
        finally:
            await page.close()
            
    async def check_rate_limit(self, session_id: str) -> bool:
        """
        Check if request is within rate limits.
        
        Args:
            session_id: Session making the request
            
        Returns:
            True if request is allowed
        """
        now = datetime.now()
        minute_ago = now - timedelta(minutes=1)
        
        if session_id not in self._rate_limits:
            self._rate_limits[session_id] = []
            
        # Clean old entries
        self._rate_limits[session_id] = [
            ts for ts in self._rate_limits[session_id] 
            if ts > minute_ago
        ]
        
        if len(self._rate_limits[session_id]) >= self._max_requests_per_minute:
            return False
            
        self._rate_limits[session_id].append(now)
        return True
        
    def get_session(self, session_id: str) -> Optional[dict]:
        """Get session information."""
        return self._sessions.get(session_id)
        
    def list_sessions(self) -> List[str]:
        """List all active session IDs."""
        return list(self._sessions.keys())
        
    async def refresh_session(self, session_id: str) -> bool:
        """
        Refresh session to maintain activity.
        
        Args:
            session_id: Session to refresh
            
        Returns:
            True if refresh successful
        """
        if session_id not in self._sessions:
            return False
            
        self._sessions[session_id]['last_activity'] = datetime.now()
        return True
