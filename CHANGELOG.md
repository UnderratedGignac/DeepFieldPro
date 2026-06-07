# DeepFieldPro Changelog

## [Unreleased] - 2026-06-07
### Added
- **Prop Betting Markets**: The AI daemon now evaluates and officially places bets on `Corners (Over 8.5)`, `Player Shots (Over 1.5)`, and `Anytime Goalscorer` markets based on statistical edge.
- **Strict Lineup Validation**: Added a strict filter to the betting loop. Matches that do not have confirmed 11-man lineups are now skipped entirely, preventing the AI from betting on estimated or unverified data.

### Changed
- **Bankroll Limit Enforcement**: The AI's betting loop now explicitly integrates with the `bankroll_tracker`'s `register_bet()` function. The stake is deducted from the current balance at the time of execution. If the balance falls to $0, further bets are physically blocked.
- **Capital Adjustment**: Increased the daily exposure maximum (`MAX_DAILY_EXPOSURE_PCT`) from 10% to 100%, allowing the AI to utilize its full $100 starting balance in a single day if it identifies enough value.
- **Database Reset**: Purged and completely reset all `data/*.db` sqlite databases (bankroll, bet logs, predictions, caches) to enforce a fresh slate starting at exactly $100.

### Fixed
- **UI Crash with Historical Predictions**: Fixed a critical bug in `src/templates/index.html` where the live dashboard crashed and failed to render games due to a `TypeError` (`Cannot read properties of undefined (reading 'toFixed')`). The frontend now gracefully handles dynamically updated predictions without cached odds data by defaulting them to `0.00`.
- **Database Thread Locking**: Mitigated SQLite lock contention between the background Scraper loop and the Live Dashboard Server API by ensuring connections are closed prior to network I/O requests.
- **Hardcoded Match Removal**: Removed the hardcoded "Simulated Demo" match injection from the Live Dashboard Server. The UI now dynamically renders the live pipeline's true state without spoofed placeholders.
