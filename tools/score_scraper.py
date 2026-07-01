"""
score_scraper.py
================
Playwright-based score lookup for matches the standard sources miss.

Flow per match:
  1. Google-search "{home} vs {away} result full time"
  2. Parse score from page title or Google's inline sports card
  3. If still nothing → navigate to the first organic result link (usually Sofascore)
  4. Parse score from that page's title / visible elements
  5. Return {"home_score": int, "away_score": int, "source": str} or None

Usage (standalone):
    .venv\\Scripts\\python.exe tools\\score_scraper.py "Arsenal" "Chelsea"
"""

import re
import sys
from urllib.parse import quote_plus

from playwright.sync_api import sync_playwright, Page

# Matches "2 - 1", "0:3", "1 – 0", "2-1" etc.; rejects lines like "90+3"
_SCORE_RE = re.compile(r'(?<!\d)(\d{1,2})\s*[-–:]\s*(\d{1,2})(?!\d)')


def _find_score(text: str) -> tuple[int, int] | None:
    """Return first plausible football score found in text, or None."""
    for m in _SCORE_RE.finditer(text):
        h, a = int(m.group(1)), int(m.group(2))
        # Sanity: max realistic football score per team is 15
        if h <= 15 and a <= 15:
            return h, a
    return None


def _is_valid_match_url(url: str) -> bool:
    """Return False for pages that are team/league overviews, not specific match pages."""
    # Sofascore team or category pages — these don't show a specific match score
    if "sofascore.com" in url:
        if "/team/" in url or "/tournament/" in url or "/category/" in url:
            return False
        if "/match/" not in url and "/event/" not in url:
            return False
    if "flashscore" in url and "/team/" in url:
        return False
    return True


def _first_external_link(page: Page) -> str | None:
    """Return href of the first organic Google result (skips google.com links)."""
    candidates = [
        "div.g a[href^='http']",
        "#search a[href^='http']",
        "a[data-ved][href^='http']",
    ]
    for sel in candidates:
        try:
            for loc in page.locator(sel).all():
                href = loc.get_attribute("href") or ""
                if href and "google.com" not in href and "googleadservices" not in href:
                    return href
        except Exception:
            pass
    return None


def _teams_and_score_from_title(title: str) -> tuple[str, int, int, str] | None:
    """
    Try to parse 'Team A N - M Team B' from a page title.
    Returns (team1, score1, score2, team2) or None.
    """
    # Sofascore format: "Team A 2 - 1 Team B | SofaScore"
    # Flashscore:       "Team A - Team B 2:1"
    m = re.search(r'(.+?)\s+(\d{1,2})\s*[-–:]\s*(\d{1,2})\s+(.+?)(?:\s*\||\s*-\s*Sof|\s*$)', title)
    if m:
        t1   = m.group(1).strip()
        s1   = int(m.group(2))
        s2   = int(m.group(3))
        t2   = m.group(4).strip()
        if s1 <= 20 and s2 <= 20:
            return t1, s1, s2, t2
    return None


def _score_from_page(page: Page, source_url: str) -> tuple[int, int] | None:
    """Try to extract a final score from the current page."""
    # 1. Page title (Sofascore: "Arsenal 2 - 1 Chelsea | SofaScore")
    score = _find_score(page.title())
    if score:
        return score

    # 2. Sofascore / Flashscore specific elements
    selectors = [
        "[data-testid='event-score']",
        "[class*='Score']",
        "[class*='score']",
        ".event__score",
        "bdi",
        "[class*='result']",
    ]
    for sel in selectors:
        try:
            locs = page.locator(sel).all()[:12]
            combined = " ".join(loc.inner_text() for loc in locs)
            score = _find_score(combined)
            if score:
                return score
        except Exception:
            pass

    # 3. Scan the first 8 000 chars of body text
    try:
        body = page.locator("body").inner_text()[:8000]
        # Look for score on its own line (avoids false positives like "90 - 45 min")
        for line in body.splitlines():
            line = line.strip()
            if _SCORE_RE.fullmatch(line):
                score = _find_score(line)
                if score:
                    return score
        # Broader scan
        score = _find_score(body)
        if score:
            return score
    except Exception:
        pass

    return None


def scrape_score(
    home: str,
    away: str,
    headless: bool = True,
    timeout_ms: int = 30_000,
) -> dict | None:
    """
    Find the final score for `home vs away`.

    Returns::
        {"home_score": int, "away_score": int, "source": str}
    or None if no score was found.
    """
    query = f"{home} vs {away} result full time score"
    search_url = f"https://www.google.com/search?q={quote_plus(query)}&hl=en&gl=us"

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
        )
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="en-US",
        )
        page = ctx.new_page()

        try:
            # ── Step 1: Google search ──────────────────────────────────────
            print(f"  [scraper] Google: {query}")
            page.goto(search_url, timeout=timeout_ms, wait_until="domcontentloaded")
            page.wait_for_timeout(2_500)

            # Check title first (Google sometimes shows score there)
            score = _find_score(page.title())
            if score:
                browser.close()
                return {
                    "home_score": score[0],
                    "away_score": score[1],
                    "source": "google_title",
                }

            # Scan Google's sports / knowledge panel
            try:
                body = page.locator("body").inner_text()
                for line in body.splitlines():
                    line = line.strip()
                    if _SCORE_RE.fullmatch(line):
                        score = _find_score(line)
                        if score:
                            browser.close()
                            return {
                                "home_score": score[0],
                                "away_score": score[1],
                                "source": "google_card",
                            }
            except Exception:
                pass

            # ── Step 2: Follow first organic link ─────────────────────────
            first_link = _first_external_link(page)
            if not first_link:
                browser.close()
                return None

            if not _is_valid_match_url(first_link):
                print(f"  [scraper] skip non-match URL: {first_link[:80]}")
                browser.close()
                return None

            print(f"  [scraper] -> {first_link[:90]}")
            page.goto(first_link, timeout=timeout_ms, wait_until="domcontentloaded")
            # Sofascore is JS-heavy — give it time to hydrate
            page.wait_for_timeout(4_000)

            page_title = page.title()
            score = _score_from_page(page, first_link)
            browser.close()

            if score:
                return {
                    "home_score": score[0],
                    "away_score": score[1],
                    "source": first_link,
                    "page_title": page_title,
                }
            return None

        except Exception as e:
            print(f"  [scraper] error: {e}")
            try:
                browser.close()
            except Exception:
                pass
            return None


# ── CLI helper ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: score_scraper.py <home_team> <away_team>")
        sys.exit(1)
    home_arg, away_arg = sys.argv[1], sys.argv[2]
    print(f"Looking up: {home_arg} vs {away_arg}")
    result = scrape_score(home_arg, away_arg, headless=True)
    if result:
        print(f"Score: {result['home_score']} - {result['away_score']}  (source: {result['source']})")
    else:
        print("Score not found.")
