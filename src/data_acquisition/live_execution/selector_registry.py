# selector_registry.py
import logging

logger = logging.getLogger(__name__)

class SelectorRegistry:
    """
    Centralized selector management.
    Sportsbooks mutate frontend structures frequently.
    We prefer data-attributes, ARIA labels, and semantic hierarchy over raw CSS classes.
    """
    def __init__(self):
        self.SELECTORS = {
            # Betarabia specific locators (mocked for production mapping)
            "market_container": "data-test-id='market-accordion-{market_id}'",
            "player_row": "role='button' >> text='{player_name}'",
            "odds_button": "data-test-id='odds-btn-{selection_id}'",
            "betslip_container": "data-test-id='betslip-drawer'",
            "stake_input": "data-test-id='stake-input-{selection_id}'",
            "confirm_button": "button >> text='Place Bet'",
            "success_toast": "data-test-id='bet-receipt-success'",
            "suspension_overlay": "data-test-id='market-suspended-overlay'",
            "loading_spinner": ".loader-spinner" # Fallback to class if needed
        }

    def get(self, key: str, **kwargs) -> str:
        """
        Retrieves a selector and formats it with dynamic kwargs (like player_name).
        """
        selector = self.SELECTORS.get(key)
        if not selector:
            logger.error(f"[SELECTOR REGISTRY] Missing selector for key: {key}")
            raise KeyError(f"Selector {key} not found.")
        
        try:
            return selector.format(**kwargs)
        except KeyError as e:
            logger.error(f"[SELECTOR REGISTRY] Missing format kwarg {e} for selector {key}")
            raise

registry = SelectorRegistry()
