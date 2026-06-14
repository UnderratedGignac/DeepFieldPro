-- Migration: 001_advanced_markets.sql
-- Description: Schema changes for DeepFieldPro Advanced Simulation Engine

-- 1. Expanded Team Stats Table
CREATE TABLE IF NOT EXISTS team_stats (
    team_id VARCHAR(50) PRIMARY KEY,
    team_name VARCHAR(100),
    league VARCHAR(50),
    form_last_5 REAL,        -- e.g. rolling points
    xg_for_p90 REAL,
    xg_against_p90 REAL,
    possession_pct REAL,
    pressing_intensity REAL, -- PPDA (Passes allowed Per Defensive Action)
    corners_for_p90 REAL,
    corners_against_p90 REAL,
    yellow_cards_p90 REAL,
    red_cards_p90 REAL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Expanded Player Stats Table
CREATE TABLE IF NOT EXISTS player_stats (
    player_id VARCHAR(50) PRIMARY KEY,
    player_name VARCHAR(100),
    team_id VARCHAR(50) REFERENCES team_stats(team_id),
    position VARCHAR(10),
    age INTEGER,
    minutes_played INTEGER,
    goals_p90 REAL,
    assists_p90 REAL,
    xg_p90 REAL,
    xa_p90 REAL,
    shots_p90 REAL,
    sot_p90 REAL,            -- Shots on target
    passes_p90 REAL,
    tackles_p90 REAL,
    fouls_committed_p90 REAL,
    fouls_drawn_p90 REAL,
    yellow_cards_p90 REAL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Match Context Table
CREATE TABLE IF NOT EXISTS match_context (
    fixture_id VARCHAR(100) PRIMARY KEY,
    home_team_id VARCHAR(50) REFERENCES team_stats(team_id),
    away_team_id VARCHAR(50) REFERENCES team_stats(team_id),
    kickoff_time TIMESTAMP,
    home_rest_days INTEGER,
    away_rest_days INTEGER,
    weather_condition VARCHAR(50), -- e.g. 'Rain', 'Clear'
    home_key_injuries INTEGER,     -- Count of key missing players
    away_key_injuries INTEGER,
    closing_odds_home REAL,
    closing_odds_draw REAL,
    closing_odds_away REAL,
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Player Similarity Index (For handling [MISSING] players)
CREATE TABLE IF NOT EXISTS player_similarity_index (
    player_id VARCHAR(50) PRIMARY KEY REFERENCES player_stats(player_id),
    pca_vector_1 REAL,
    pca_vector_2 REAL,
    pca_vector_3 REAL,
    cluster_id INTEGER,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
