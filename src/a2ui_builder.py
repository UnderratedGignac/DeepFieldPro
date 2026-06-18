"""A2UI v0.9 builder for DeepFieldPro dashboard.

Converts the flat match-list state into a structured A2UI v0.9 message that
agent-to-user-interface clients can render as native components.
"""

from __future__ import annotations

from typing import Any


def _summary(matches: list) -> str:
    """Return a one-line summary of today's fixture list."""
    if not matches:
        return "No fixtures — is the daemon running?"

    n = len(matches)

    rec = sum(1 for m in matches if m.get("recommended") or m.get("is_recommended"))

    steam_hits = sum(1 for m in matches if abs(m.get("steam_move") or 0) >= 3.0)

    return f"{n} fixtures today · {rec} AI picks · {steam_hits} steam signals >=3%"


def _match_card_components(match: dict, idx: int) -> list[dict]:
    """Return the list of component dicts for a single match card."""
    home = match.get("home_team") or match.get("home") or "Home"
    away = match.get("away_team") or match.get("away") or "Away"
    match_label = f"{home} vs {away}"

    # --- probabilities ---
    raw_h = (
        match.get("home_win_prob")
        or match.get("home_prob")
        or match.get("h_prob")
        or 0.0
    )
    raw_d = match.get("draw_prob") or match.get("d_prob") or 0.0
    raw_a = (
        match.get("away_win_prob")
        or match.get("away_prob")
        or match.get("a_prob")
        or 0.0
    )

    # scale from [0,1] to percentage if needed
    if (
        raw_h <= 1.0
        and raw_d <= 1.0
        and raw_a <= 1.0
        and (raw_h + raw_d + raw_a) <= 1.05
    ):
        h_pct = raw_h * 100
        d_pct = raw_d * 100
        a_pct = raw_a * 100
    else:
        h_pct = raw_h
        d_pct = raw_d
        a_pct = raw_a

    probs_text = f"H:{h_pct:.0f}% D:{d_pct:.0f}% A:{a_pct:.0f}%"

    # --- EV & steam ---
    ev = match.get("ev") or match.get("expected_value") or 0.0
    steam = match.get("steam_move") or 0.0
    recommended = bool(match.get("recommended") or match.get("is_recommended"))

    ev_parts = [f"EV: {ev:+.1f}%"]
    if abs(steam) >= 2.0:
        ev_parts.append(f"Steam: {steam:+.1f}%")
    if recommended:
        ev_parts.append("RECOMMENDED")

    ev_text = " · ".join(ev_parts)

    prefix = f"card-{idx}"

    components = [
        {
            "id": prefix,
            "component": "Card",
            "children": [f"match-{idx}", f"probs-{idx}", f"ev-{idx}"],
        },
        {
            "id": f"match-{idx}",
            "component": "Text",
            "text": match_label,
            "variant": "h2",
        },
        {
            "id": f"probs-{idx}",
            "component": "Text",
            "text": probs_text,
        },
        {
            "id": f"ev-{idx}",
            "component": "Text",
            "text": ev_text,
            "variant": "caption",
        },
    ]

    return components


def build_dashboard_ui(
    matches: list,
    settings: dict | None = None,
    bankroll: float = 0.0,
) -> dict:
    """Build a complete A2UI v0.9 message for the current dashboard state.

    Args:
        matches: List of match dicts from todays_dashboard_state.json.
        settings: Optional settings dict (currently unused, reserved for future).
        bankroll: Current paper bankroll balance.

    Returns:
        A dict conforming to the A2UI v0.9 envelope.
    """
    components: list[dict[str, Any]] = []

    # ---- root ----
    components.append(
        {
            "id": "root",
            "component": "Column",
            "children": ["header", "summary", "cards-list"],
        }
    )

    # ---- header row ----
    components.append(
        {
            "id": "header",
            "component": "Row",
            "children": ["title", "bal"],
        }
    )
    components.append(
        {
            "id": "title",
            "component": "Text",
            "text": "Today's Picks",
            "variant": "h1",
        }
    )
    balance_str = f"Balance: ${bankroll:,.2f}" if bankroll else "Balance: —"
    components.append(
        {
            "id": "bal",
            "component": "Text",
            "text": balance_str,
        }
    )

    # ---- summary ----
    components.append(
        {
            "id": "summary",
            "component": "Text",
            "text": _summary(matches),
        }
    )

    # ---- match cards list ----
    card_ids: list[str] = []
    for idx, match in enumerate(matches or []):
        card_components = _match_card_components(match, idx)
        components.extend(card_components)
        card_ids.append(f"card-{idx}")

    components.append(
        {
            "id": "cards-list",
            "component": "List",
            "children": card_ids,
        }
    )

    return {
        "version": "v0.9",
        "updateComponents": {
            "surfaceId": "main",
            "components": components,
        },
    }
