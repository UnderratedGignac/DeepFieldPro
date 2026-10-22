# Crowd Bets Scraper — Design Spec
**Date:** 2026-07-01  
**Status:** Approved

## Goal
Paper-bet every prediction from every free crowd/tipster source across all available markets for research data collection. No real money. Maximum bet diversity.

## Module
`src/crowd_bets_scraper.py`

## Sources

| Class | Site | Markets |
|---|---|---|
| `SofascoreOddsSource` | sofascore.com odds API | 1X2, O/U 1.5/2.5/3.5, AH, BTTS, DC, DNB, Correct Score, HT/FT, 1st to Score |
| `SofascoreVotesSource` | sofascore.com/api/v1/event/{id}/votes | 1X2 crowd % |
| `ForebetSource` | forebet.com | 1X2, O/U 2.5, BTTS, Correct Score, HT/FT |
| `FootyStatsSource` | footystats.org | BTTS, O/U lines, Corners, Cards, Clean Sheet, Win to Nil |
| `WindrawwinSource` | windrawwin.com | 1X2, O/U 2.5, BTTS, AH |

## Staking
`stake = settings["crowd_base_stake"] * (confidence_pct / 100)`  
Default `crowd_base_stake = 25`. Confidence = de-vigged implied prob (odds sources) or crowd % (vote/tipster sources).

## Bet Source Tags
`CROWD_SF_ODDS`, `CROWD_SF_VOTES`, `CROWD_FB`, `CROWD_FS`, `CROWD_WDW`

## Dedup
One open bet per `fixture_id × market_type × side × bet_source`.

## Daemon Hook
Called once per cycle from `run_prediction_cycle()` after AI bets.

## Settlement
Existing `settle_open_bets()` handles 1X2, O/U, BTTS. Correct Score and HT/FT get new settlement branches.
