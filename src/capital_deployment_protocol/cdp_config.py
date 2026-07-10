"""
Capital Deployment Protocol Configuration

Centralized configuration for all CDP parameters to eliminate hardcoding
and enable easy tuning for optimal performance.
"""

import os
from typing import Dict


class CDPConfig:
    """
    Configuration for Capital Deployment Protocol.
    
    All values can be overridden via environment variables for easy tuning
    without code changes. This is critical for finding optimal parameters
    through experimentation and avoiding hardcoded assumptions.
    """
    
    # ===== BANKROLL CONFIGURATION =====
    # CRITICAL: Must match your actual trading bankroll
    TARGET_BANKROLL = float(os.getenv("CDP_TARGET_BANKROLL", "10000.0"))
    
    # ===== PHASE TRANSITION THRESHOLDS =====
    # Minimum days required in each phase before promotion
    PHASE_0_MIN_DAYS = int(os.getenv("CDP_PHASE_0_MIN_DAYS", "14"))
    PHASE_1_MIN_DAYS = int(os.getenv("CDP_PHASE_1_MIN_DAYS", "7"))
    PHASE_2_MIN_DAYS = int(os.getenv("CDP_PHASE_2_MIN_DAYS", "14"))
    PHASE_3_MIN_DAYS = int(os.getenv("CDP_PHASE_3_MIN_DAYS", "0"))
    
    # Maximum allowable drawdown in each phase (as decimal)
    # Tighter constraints in early phases protect against premature scaling
    PHASE_0_MAX_DRAWDOWN = float(os.getenv("CDP_PHASE_0_MAX_DRAWDOWN", "0.0"))
    PHASE_1_MAX_DRAWDOWN = float(os.getenv("CDP_PHASE_1_MAX_DRAWDOWN", "0.05"))
    PHASE_2_MAX_DRAWDOWN = float(os.getenv("CDP_PHASE_2_MAX_DRAWDOWN", "0.10"))
    PHASE_3_MAX_DRAWDOWN = float(os.getenv("CDP_PHASE_3_MAX_DRAWDOWN", "0.15"))
    
    # ===== CAPITAL ALLOCATION CAPS =====
    # Percentage of target bankroll allocated at each phase
    # Conservative ramp prevents catastrophic early losses
    PHASE_0_CAP_PCT = float(os.getenv("CDP_PHASE_0_CAP_PCT", "0.0"))
    PHASE_1_CAP_PCT = float(os.getenv("CDP_PHASE_1_CAP_PCT", "0.01"))  # 1%
    PHASE_2_CAP_PCT = float(os.getenv("CDP_PHASE_2_CAP_PCT", "0.15"))  # 15%
    PHASE_3_CAP_PCT = float(os.getenv("CDP_PHASE_3_CAP_PCT", "1.0"))   # 100%
    
    # ===== RAMP CONTROLLER PARAMETERS =====
    # Logistic curve parameters for smooth capital ramp within phases
    # k=steepness, t0=midpoint (day when ramp reaches 50% of cap)
    RAMP_STEEPNESS = float(os.getenv("CDP_RAMP_STEEPNESS", "0.5"))
    RAMP_MIDPOINT_DAY = float(os.getenv("CDP_RAMP_MIDPOINT_DAY", "7.0"))
    
    # ACSI velocity modulation bounds
    # Controls how much ACSI signal can scale the capital ceiling
    ACSI_VELOCITY_MIN = float(os.getenv("CDP_ACSI_VELOCITY_MIN", "-0.10"))
    ACSI_VELOCITY_MAX = float(os.getenv("CDP_ACSI_VELOCITY_MAX", "0.10"))
    ACSI_MULTIPLIER_MIN = float(os.getenv("CDP_ACSI_MULTIPLIER_MIN", "0.5"))
    ACSI_MULTIPLIER_MAX = float(os.getenv("CDP_ACSI_MULTIPLIER_MAX", "1.5"))
    ACSI_MULTIPLIER_SCALE = float(os.getenv("CDP_ACSI_MULTIPLIER_SCALE", "5.0"))
    
    # ===== HEALTH STATUS THRESHOLDS =====
    # Drawdown thresholds that trigger health status changes
    HEALTH_HEALTHY_THRESHOLD = float(os.getenv("CDP_HEALTH_HEALTHY_THRESHOLD", "0.05"))
    HEALTH_DEGRADED_THRESHOLD = float(os.getenv("CDP_HEALTH_DEGRADED_THRESHOLD", "0.12"))
    # >= CRITICAL_THRESHOLD triggers shutdown
    
    # ===== POSITION SIZING MULTIPLIERS =====
    # Risk multipliers by market regime (lower = more conservative)
    # These should be calibrated based on historical performance by regime
    REGIME_MULTIPLIERS: Dict[str, float] = {
        "stable": float(os.getenv("CDP_REGIME_STABLE_MULT", "1.0")),
        "reactive": float(os.getenv("CDP_REGIME_REACTIVE_MULT", "0.6")),
        "high-frequency-volatility": float(
            os.getenv("CDP_REGIME_HFV_MULT", "0.25")
        ),
        "panic": float(os.getenv("CDP_REGIME_PANIC_MULT", "0.05")),
    }
    
    # Single bet limit as percentage of phase capital
    # Prevents over-concentration in any single position
    MAX_SINGLE_BET_PCT = float(os.getenv("CDP_MAX_SINGLE_BET_PCT", "0.10"))
    
    # ===== KILL SWITCH CONFIGURATION =====
    # RVL signals that allow execution
    ALLOWED_RVL_SIGNALS = [
        "READY_FOR_CAPITAL",
        "CONDITIONALLY_READY",
    ]
    
    @classmethod
    def get_phase_min_days(cls, phase_name: str) -> int:
        """Get minimum days for a specific phase."""
        mapping = {
            "PHASE_0_SHADOW": cls.PHASE_0_MIN_DAYS,
            "PHASE_1_MICRO": cls.PHASE_1_MIN_DAYS,
            "PHASE_2_LIMITED": cls.PHASE_2_MIN_DAYS,
            "PHASE_3_PRODUCTION": cls.PHASE_3_MIN_DAYS,
        }
        return mapping.get(phase_name, 0)
    
    @classmethod
    def get_phase_max_drawdown(cls, phase_name: str) -> float:
        """Get maximum drawdown for a specific phase."""
        mapping = {
            "PHASE_0_SHADOW": cls.PHASE_0_MAX_DRAWDOWN,
            "PHASE_1_MICRO": cls.PHASE_1_MAX_DRAWDOWN,
            "PHASE_2_LIMITED": cls.PHASE_2_MAX_DRAWDOWN,
            "PHASE_3_PRODUCTION": cls.PHASE_3_MAX_DRAWDOWN,
        }
        return mapping.get(phase_name, 0.15)
    
    @classmethod
    def get_phase_cap_pct(cls, phase_name: str) -> float:
        """Get capital allocation percentage for a specific phase."""
        mapping = {
            "PHASE_0_SHADOW": cls.PHASE_0_CAP_PCT,
            "PHASE_1_MICRO": cls.PHASE_1_CAP_PCT,
            "PHASE_2_LIMITED": cls.PHASE_2_CAP_PCT,
            "PHASE_3_PRODUCTION": cls.PHASE_3_CAP_PCT,
        }
        return mapping.get(phase_name, 0.0)
    
    @classmethod
    def get_regime_multiplier(cls, regime: str) -> float:
        """Get risk multiplier for a specific market regime."""
        return cls.REGIME_MULTIPLIERS.get(regime, 0.0)
    
    @classmethod
    def validate(cls) -> bool:
        """
        Validate configuration for common mistakes.
        Returns True if valid, raises ValueError if invalid.
        """
        if cls.TARGET_BANKROLL <= 0:
            raise ValueError("TARGET_BANKROLL must be positive")
        
        if not (0 <= cls.PHASE_0_CAP_PCT <= cls.PHASE_1_CAP_PCT <= 
                cls.PHASE_2_CAP_PCT <= cls.PHASE_3_CAP_PCT <= 1.0):
            raise ValueError("Phase caps must be non-decreasing and <= 1.0")
        
        if not (0 <= cls.PHASE_0_MAX_DRAWDOWN <= cls.PHASE_1_MAX_DRAWDOWN <= 
                cls.PHASE_2_MAX_DRAWDOWN <= cls.PHASE_3_MAX_DRAWDOWN):
            raise ValueError("Phase drawdowns must be non-decreasing")
        
        if cls.ACSI_MULTIPLIER_MIN > cls.ACSI_MULTIPLIER_MAX:
            raise ValueError("ACSI multiplier bounds invalid")
        
        for regime, mult in cls.REGIME_MULTIPLIERS.items():
            if not (0 <= mult <= 1.0):
                raise ValueError(f"Regime multiplier for {regime} must be in [0, 1]")
        
        return True


# Global config instance
cdp_config = CDPConfig()

# Validate on import to catch configuration errors early
try:
    cdp_config.validate()
except ValueError as e:
    import warnings
    warnings.warn(f"CDP Configuration validation failed: {e}")
