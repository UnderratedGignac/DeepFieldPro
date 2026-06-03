# DeepField Pro - Architecture Documentation

## Overview

DeepField Pro is a sophisticated sports betting analytics and execution platform that combines real-time odds acquisition, machine learning predictions, and automated bankroll management.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     DeepField Pro System                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │   Session    │    │    Odds      │    │  Normalizer  │      │
│  │   Manager    │───▶│  Collector   │───▶│    Engine    │      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
│         │                   │                   │               │
│         │                   │                   ▼               │
│         │                   │          ┌──────────────┐         │
│         │                   └─────────▶│  Database    │         │
│         │                              │   (PostgreSQL)│        │
│         │                              └──────────────┘         │
│         │                                       │               │
│         ▼                                       ▼               │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │   Browser    │    │  Prediction  │    │   Execution  │      │
│  │   Engine     │    │   Engine     │    │    Engine    │      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
│                              │                   │               │
│                              ▼                   ▼               │
│                       ┌──────────────┐    ┌──────────────┐      │
│                       │     ML       │    │  Bankroll    │      │
│                       │   Models     │    │  Management  │      │
│                       └──────────────┘    └──────────────┘      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Core Services

### 1. Session Manager (`src/services/session_manager/`)

**Purpose**: Manages browser sessions for web-based odds acquisition from sportsbooks.

**Components**:
- `browser_engine.py`: Playwright-based browser automation with stealth capabilities
- `service.py`: Session lifecycle management, authentication, and rate limiting

**Key Features**:
- Multi-context browser instances for parallel sportsbook access
- Cookie persistence and session state management
- Rate limiting per sportsbook to avoid detection
- Stealth browsing to circumvent bot detection

### 2. Odds Acquisition (`src/services/odds_acquisition/`)

**Purpose**: Collects real-time odds data from multiple sportsbooks.

**Components**:
- `collector.py`: Orchestrates odds collection across configured sportsbooks

**Key Features**:
- Simultaneous data collection from multiple sources
- Error handling and retry logic
- Timestamp tracking for odds movement analysis
- Support for major sportsbooks (Bet365, Pinnacle, Betfair, etc.)

### 3. Normalizer Engine (`src/services/normalizer/`)

**Purpose**: Standardizes odds data from different sportsbooks into a unified format.

**Components**:
- `engine.py`: Market mapping, odds conversion, and validation

**Key Features**:
- Market name standardization across sportsbooks
- Odds format conversion (decimal, fractional, American)
- Data validation and cleaning
- Arbitrage opportunity detection

### 4. Configuration (`src/config/`)

**Purpose**: Centralized configuration management.

**Components**:
- `settings.py`: Environment-based configuration with sensible defaults

**Key Features**:
- Environment variable overrides
- Directory management
- API key management
- Risk parameter configuration

### 5. Database Models (`src/database/`)

**Purpose**: Data persistence layer using SQLAlchemy ORM.

**Components**:
- `models.py`: SQLAlchemy models for fixtures, odds, predictions, and bets

**Schema**:
- **fixtures**: Match information and results
- **odds**: Historical odds snapshots from all sportsbooks
- **predictions**: Model predictions with confidence scores
- **bets**: Placed bet tracking and results
- **bankroll_snapshots**: Bankroll history over time

## Data Flow

1. **Odds Collection Cycle**:
   ```
   Session Manager creates browser sessions
         ↓
   Odds Collector fetches raw odds from sportsbooks
         ↓
   Normalizer Engine standardizes the data
         ↓
   Data stored in PostgreSQL database
   ```

2. **Prediction Generation**:
   ```
   Historical odds + fixture data loaded
         ↓
   ML models generate predictions
         ↓
   Kelly criterion calculates optimal stakes
         ↓
   Predictions stored for execution
   ```

3. **Bet Execution**:
   ```
   Value bets identified (fair odds > market odds)
         ↓
   Risk engine validates against exposure limits
         ↓
   Execution engine places bets via API/browser
         ↓
   Results tracked and logged
   ```

## Deployment

### Docker Compose

The system uses Docker Compose for orchestrated deployment:

```yaml
Services:
- db: PostgreSQL database
- odds_collector: Real-time odds collection
- session_manager: Browser session management
- normalizer: Data normalization
- predictor: ML prediction generation
```

### Environment Variables

Key configuration via `.env`:
- API keys for data providers
- Betfair credentials
- Bankroll parameters
- Browser settings
- Logging configuration

## Security Considerations

1. **Credential Management**: All sensitive data via environment variables
2. **Rate Limiting**: Built-in protection against sportsbook bans
3. **Stealth Browsing**: Anti-detection measures for web scraping
4. **Database Security**: Isolated PostgreSQL with strong passwords

## Monitoring & Telemetry

The system includes comprehensive telemetry:
- Execution success/failure rates
- Odds movement tracking
- Bankroll evolution
- Model performance metrics
- Sportsbook behavior fingerprinting

## Extensibility

### Adding New Sportsbooks

1. Add sportsbook to collector configuration
2. Implement parsing logic for new DOM structure
3. Add market mappings to normalizer

### Adding New Markets

1. Update market mappings in normalizer
2. Configure in prediction models
3. Add to database schema if needed

## Performance Optimization

- Async I/O for concurrent odds collection
- Connection pooling for database access
- Browser context reuse for efficiency
- Intelligent caching of session states

---

*Last Updated: 2024*
*Version: 1.0.0*
