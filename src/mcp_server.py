"""
DeepFieldPro MCP Server
Exposes DeepFieldPro databases and analytics tools as MCP tools for Claude Code.
"""

import sqlite3
import json
import subprocess
from pathlib import Path

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    raise ImportError("Run: .venv/Scripts/pip.exe install mcp>=1.0.0")

mcp = FastMCP("DeepFieldPro")
BASE = Path(__file__).parent.parent
DATA = BASE / "data"
TOOLS_DIR = BASE / "tools"
VENV_PYTHON = BASE / ".venv" / "Scripts" / "python.exe"

TOOL_WHITELIST = {
    "steam_report.py",
    "clv_report.py",
    "league_report.py",
    "settlement_audit.py",
    "backtest.py",
}


def _safe_query(db_path: Path, sql: str, max_rows: int = 500) -> str:
    if not sql.strip().upper().startswith("SELECT"):
        return json.dumps({"error": "Only SELECT queries allowed"})
    if not db_path.exists():
        return json.dumps({"error": f"DB not found: {db_path.name}"})
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql).fetchmany(max_rows)
        conn.close()
        return json.dumps([dict(r) for r in rows], default=str, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def query_odds_db(sql: str) -> str:
    """Query odds_stream.db (tables: fixture, market). SELECT only. Returns JSON array.

    Tables:
      fixture(fixture_id, home_team, away_team, kickoff_time, kickoff_date,
              league_id, tournament_name, scraped_at)
      market(fixture_id, market_type, selection, odds, last_updated)

    Max 500 rows returned.
    """
    return _safe_query(DATA / "odds_stream.db", sql)


@mcp.tool()
def query_bet_log(sql: str) -> str:
    """Query bet_log.db (tables: bet_log, odds_history, steam_signals). SELECT only. Returns JSON array.

    Tables:
      bet_log(id, match, market_type, side, odds, stake, bet_source, timestamp,
              result, clv, fixture_id, league)
      odds_history(fixture_id, market, selection, odds, timestamp)
      steam_signals(fixture_id, league, market, selection, odds, move, kickoff)

    Max 500 rows returned.
    """
    return _safe_query(DATA / "bet_log.db", sql)


@mcp.tool()
def query_bankroll(sql: str) -> str:
    """Query bankroll.db (table: bankroll). SELECT only. Returns JSON array.

    Tables:
      bankroll(date, current_balance, total_invested, net_pnl)

    Max 500 rows returned.
    """
    return _safe_query(DATA / "bankroll.db", sql)


@mcp.tool()
def get_dashboard_state() -> str:
    """Read and return the current dashboard state from data/todays_dashboard_state.json.

    Returns the full JSON content of the dashboard state file, which contains
    today's match predictions, recommendations, and model outputs.
    """
    try:
        state_path = DATA / "todays_dashboard_state.json"
        if not state_path.exists():
            return json.dumps({"error": "todays_dashboard_state.json not found"})
        content = state_path.read_text(encoding="utf-8")
        # Parse and re-serialize to validate JSON and normalize formatting
        parsed = json.loads(content)
        return json.dumps(parsed, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def get_settings() -> str:
    """Read and return settings from data/settings.json.

    Controls Kelly multiplier, EV/confidence thresholds, allowed markets,
    auto_place_bets, and steam detection settings.
    """
    try:
        settings_path = DATA / "settings.json"
        if settings_path.exists():
            result = {"settings": json.loads(settings_path.read_text(encoding="utf-8"))}
        else:
            result = {"settings": {"error": "settings.json not found"}}

        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def run_analytics_tool(script: str) -> str:
    """Run a whitelisted analytics tool from the tools/ directory and return its stdout.

    Allowed scripts:
      - steam_report.py    : Steam signal ROI and paper-strategy P&L
      - clv_report.py      : Closing Line Value analysis for placed bets
      - league_report.py   : P&L breakdown by league
      - settlement_audit.py: Audit bet settlement accuracy
      - backtest.py        : Replay historical picks with rules + staking

    Args:
        script: Filename of the script to run (e.g. "steam_report.py")

    Returns stdout output capped at 6000 characters.
    """
    try:
        # Normalise to bare filename to prevent path traversal
        script_name = Path(script).name

        if script_name not in TOOL_WHITELIST:
            allowed = ", ".join(sorted(TOOL_WHITELIST))
            return json.dumps(
                {
                    "error": f"Script '{script_name}' is not in the whitelist. "
                    f"Allowed scripts: {allowed}"
                }
            )

        script_path = TOOLS_DIR / script_name
        if not script_path.exists():
            return json.dumps(
                {"error": f"Script not found at expected path: {script_path}"}
            )

        if not VENV_PYTHON.exists():
            return json.dumps({"error": f"Venv Python not found at: {VENV_PYTHON}"})

        result = subprocess.run(
            [str(VENV_PYTHON), str(script_path)],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(BASE),
        )

        output_parts = []
        if result.stdout:
            output_parts.append(result.stdout)
        if result.stderr:
            output_parts.append(f"\n--- STDERR ---\n{result.stderr}")

        combined = "".join(output_parts)

        cap = 6000
        if len(combined) > cap:
            combined = combined[:cap] + f"\n... [truncated at {cap} chars]"

        return json.dumps(
            {
                "script": script_name,
                "returncode": result.returncode,
                "output": combined,
            },
            indent=2,
        )
    except subprocess.TimeoutExpired:
        return json.dumps({"error": f"Script '{script}' timed out after 120 seconds"})
    except Exception as e:
        return json.dumps({"error": str(e)})


if __name__ == "__main__":
    mcp.run()
