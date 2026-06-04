import pandas as pd
import numpy as np

def calculate_fatigue_features(df: pd.DataFrame, venue_coordinates: dict = None) -> pd.DataFrame:
    """
    Engineers fatigue and scheduling context features.
    
    Expected Input DataFrame `df`:
    Must contain match-level player logs:
    ['Date', 'Player', 'Min', 'Venue_Name']
    """
    
    # Ensure Date is datetime
    df['Date'] = pd.to_datetime(df['Date'])
    
    # 1. Sort chronologically by Player
    df = df.sort_values(by=['Player', 'Date']).reset_index(drop=True)
    
    # 2. Days Since Last Match (Rest Days)
    # diff() gets the time difference between current row and previous row
    df['days_since_last_match'] = df.groupby('Player')['Date'].diff().dt.days
    
    # Cap at 30 days to prevent summer breaks from destroying the scaling
    df['days_since_last_match'] = df['days_since_last_match'].clip(upper=30).fillna(30)
    
    # 3. Matches in the Last X Days (Schedule Congestion)
    # To do this cleanly, we can set Date as index and use rolling(window='7D')
    # We only count matches where the player actually played minutes
    
    temp_df = df[['Player', 'Date', 'Min']].copy()
    temp_df['match_played'] = np.where(temp_df['Min'] > 0, 1, 0)
    
    # Ensure no exact duplicate matches on the exact same date for the same player
    temp_df = temp_df.drop_duplicates(subset=['Player', 'Date'])
    
    # Sort and set Date as index for rolling time window
    temp_df = temp_df.sort_values(by=['Player', 'Date'])
    temp_df = temp_df.set_index('Date')
    
    # Group by player, apply 7D/14D rolling sum, and shift by 1 to exclude current match
    # rolling() on a datetime index requires the index to be monotonic per group
    last_7 = temp_df.groupby('Player')['match_played'].rolling('7D').sum().groupby('Player').shift(1)
    last_14 = temp_df.groupby('Player')['match_played'].rolling('14D').sum().groupby('Player').shift(1)
    
    # Reset index to turn MultiIndex (Player, Date) back into columns
    last_7 = last_7.reset_index(name='matches_last_7_days')
    last_14 = last_14.reset_index(name='matches_last_14_days')
    
    # Merge back to main df
    df = df.merge(last_7, on=['Player', 'Date'], how='left')
    df = df.merge(last_14, on=['Player', 'Date'], how='left')
    
    df['matches_last_7_days'] = df['matches_last_7_days'].fillna(0)
    df['matches_last_14_days'] = df['matches_last_14_days'].fillna(0)
    
    # 4. Travel Distance
    df['travel_distance'] = 0.0
    
    wc_2026_venues = {
        'MetLife Stadium': (40.8128, -74.0742), 'AT&T Stadium': (32.7473, -97.0945),
        'Arrowhead Stadium': (39.0489, -94.4839), 'NRG Stadium': (29.6847, -95.4107),
        'Mercedes-Benz Stadium': (33.7554, -84.4006), 'SoFi Stadium': (33.9535, -118.3390),
        'Lincoln Financial Field': (39.9008, -75.1675), 'Lumen Field': (47.5952, -122.3316),
        "Levi's Stadium": (37.4030, -121.9698), 'Gillette Stadium': (42.0909, -71.2643),
        'Hard Rock Stadium': (25.9580, -80.2389), 'BC Place': (49.2768, -123.1120),
        'BMO Field': (43.6332, -79.4186), 'Estadio Azteca': (19.3029, -99.1505),
        'Estadio BBVA': (25.6698, -100.2444), 'Estadio Akron': (20.6817, -103.4626)
    }
    
    all_coords = {**wc_2026_venues, **(venue_coordinates or {})}
    
    if 'Venue_Name' in df.columns:
        def haversine(lat1, lon1, lat2, lon2):
            R = 6371.0 # Earth radius in kilometers
            dlat = np.radians(lat2 - lat1)
            dlon = np.radians(lon2 - lon1)
            a = np.sin(dlat / 2)**2 + np.cos(np.radians(lat1)) * np.cos(np.radians(lat2)) * np.sin(dlon / 2)**2
            c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
            return R * c
            
        df['lat'] = df['Venue_Name'].map(lambda v: all_coords.get(v, (np.nan, np.nan))[0])
        df['lon'] = df['Venue_Name'].map(lambda v: all_coords.get(v, (np.nan, np.nan))[1])
        
        df['prev_lat'] = df.groupby('Player')['lat'].shift(1)
        df['prev_lon'] = df.groupby('Player')['lon'].shift(1)
        
        mask = df['lat'].notna() & df['prev_lat'].notna()
        df.loc[mask, 'travel_distance'] = haversine(
            df.loc[mask, 'prev_lat'], df.loc[mask, 'prev_lon'],
            df.loc[mask, 'lat'], df.loc[mask, 'lon']
        )
        
        df = df.drop(columns=['lat', 'lon', 'prev_lat', 'prev_lon'])


if __name__ == "__main__":
    print("Fatigue Features Module Loaded.")
