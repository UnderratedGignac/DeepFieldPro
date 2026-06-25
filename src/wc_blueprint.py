"""
wc_blueprint.py — Flask blueprint for the WC 2026 Winner Predictor tab.

Routes:
  GET /wc          → standalone panel (embedded as iframe in the dashboard)
  GET /wc/api/predictions → JSON payload with all team win probabilities
  POST /wc/api/refresh    → force-refresh the prediction cache
"""

import logging

from flask import Blueprint, jsonify, render_template, request

logger = logging.getLogger("wc_blueprint")

wc_bp = Blueprint("wc", __name__, url_prefix="/wc")


@wc_bp.route("/", methods=["GET"])
def wc_panel():
    """Render the full-screen WC predictor panel (served in an iframe)."""
    return render_template("wc.html")


@wc_bp.route("/api/predictions", methods=["GET"])
def wc_predictions():
    """
    Return the current prediction payload as JSON.
    Query param: ?refresh=1 to force a cache bust.
    """
    try:
        from src.wc_predictor import get_predictions as _get

        force = request.args.get("refresh", "0") == "1"
        data = _get(force_refresh=force)
        return jsonify({"ok": True, "data": data})
    except Exception as e:
        logger.exception("WC predictions failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@wc_bp.route("/api/refresh", methods=["POST"])
def wc_refresh():
    """Force-refresh the prediction cache and return updated data."""
    try:
        from src.wc_predictor import get_predictions as _get

        data = _get(force_refresh=True)
        return jsonify({"ok": True, "data": data})
    except Exception as e:
        logger.exception("WC refresh failed")
        return jsonify({"ok": False, "error": str(e)}), 500
