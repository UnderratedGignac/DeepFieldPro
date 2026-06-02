# formation_impact_engine.py
import logging
from typing import Dict

logger = logging.getLogger(__name__)

class FormationImpactEngine:
    """
    Translates formation and positional context into statistical multipliers for the Pricing Engine.
    e.g., 3-5-2 wingbacks get an attacking multiplier compared to 4-3-3 fullbacks.
    """
    
    # Base multipliers (1.0 = normal baseline)
    IMPACT_MATRIX = {
        "3-5-2": {
            "wingback": {"shots": 1.4, "crosses": 1.5, "offsides": 1.2, "tackles": 0.9},
            "striker": {"shots": 1.1, "offsides": 1.3}, # Two strikers usually share load
            "center_back": {"tackles": 1.2, "passes": 1.1} # 3 at the back
        },
        "4-3-3": {
            "fullback": {"shots": 0.8, "crosses": 1.2, "offsides": 1.0, "tackles": 1.1},
            "winger": {"shots": 1.3, "offsides": 1.4}, # Inside forwards
            "striker": {"shots": 1.4, "offsides": 1.2} # Lone striker gets funnelled chances
        },
        "4-2-3-1": {
            "attacking_mid": {"shots": 1.3, "passes": 1.4}, # Number 10 is focal point
            "defensive_mid": {"tackles": 1.3, "shots": 0.6},
            "striker": {"shots": 1.3, "offsides": 1.2}
        }
    }

    @staticmethod
    def get_multipliers(formation: str, canonical_position: str) -> Dict[str, float]:
        """
        Returns a dictionary of stat multipliers based on the formation context.
        If formation or position isn't explicitly modeled, returns neutral 1.0 multipliers.
        """
        base_multipliers = {"shots": 1.0, "crosses": 1.0, "offsides": 1.0, "tackles": 1.0, "passes": 1.0}
        
        if not formation or not canonical_position:
            return base_multipliers
            
        formation_impacts = FormationImpactEngine.IMPACT_MATRIX.get(formation, {})
        position_impacts = formation_impacts.get(canonical_position, {})
        
        # Merge overrides
        for stat, multiplier in position_impacts.items():
            base_multipliers[stat] = multiplier
            
        return base_multipliers

formation_impact_engine = FormationImpactEngine()
