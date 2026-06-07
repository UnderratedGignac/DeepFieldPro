import pandas as pd
import requests
from datetime import datetime

def fetch_weather_data(lat: float, lon: float, match_date: str) -> dict:
    """
    Example integration with the Open-Meteo Historical Weather API.
    Open-Meteo is free for non-commercial use and doesn't require an API key.
    
    Returns: temperature (C), humidity (%), wind_speed (km/h), rain (mm)
    """
    try:
        # Convert match_date to YYYY-MM-DD
        date_str = pd.to_datetime(match_date).strftime('%Y-%m-%d')
        
        url = "https://archive-api.open-meteo.com/v1/archive"
        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": date_str,
            "end_date": date_str,
            "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m,rain",
            "timezone": "auto"
        }
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        # In a real pipeline, we'd match the exact kickoff hour.
        # For this example, we take the daily average/sum.
        temp = sum(data['hourly']['temperature_2m']) / 24
        humidity = sum(data['hourly']['relative_humidity_2m']) / 24
        wind = sum(data['hourly']['wind_speed_10m']) / 24
        rain = sum(data['hourly']['rain'])  # Total daily rain in mm
        
        return {
            "temperature": round(temp, 1),
            "humidity": round(humidity, 1),
            "wind_speed": round(wind, 1),
            "rain": round(rain, 1)
        }
    except Exception as e:
        print(f"Weather API Error: {e}")
        return {"temperature": 15.0, "humidity": 60.0, "wind_speed": 10.0, "rain": 0.0}

def integrate_weather_features(df: pd.DataFrame, venue_coordinates: dict) -> pd.DataFrame:
    """
    Applies the weather fetching logic to the historical dataframe.
    
    Expected Input DataFrame `df`:
    ['Date', 'Venue_Name', ...]
    """
    # Create a unique list of Match Date + Venue combinations to avoid hitting the API 22 times per match
    venue_col = 'Venue_Name' if 'Venue_Name' in df.columns else ('Venue' if 'Venue' in df.columns else None)
    if not venue_col:
        # Cannot integrate weather without venues
        return df
        
    unique_matches = df[['Date', venue_col]].drop_duplicates().dropna()
    
    weather_records = []
    
    wc_2026_venues = {
        'MetLife Stadium': (40.8128, -74.0742),
        'AT&T Stadium': (32.7473, -97.0945),
        'Arrowhead Stadium': (39.0489, -94.4839),
        'NRG Stadium': (29.6847, -95.4107),
        'Mercedes-Benz Stadium': (33.7554, -84.4006),
        'SoFi Stadium': (33.9535, -118.3390),
        'Lincoln Financial Field': (39.9008, -75.1675),
        'Lumen Field': (47.5952, -122.3316),
        "Levi's Stadium": (37.4030, -121.9698),
        'Gillette Stadium': (42.0909, -71.2643),
        'Hard Rock Stadium': (25.9580, -80.2389),
        'BC Place': (49.2768, -123.1120),
        'BMO Field': (43.6332, -79.4186),
        'Estadio Azteca': (19.3029, -99.1505),
        'Estadio BBVA': (25.6698, -100.2444),
        'Estadio Akron': (20.6817, -103.4626)
    }
    
    # In production, this loop should be parallelized/batched
    for _, row in unique_matches.iterrows():
        venue = row[venue_col]
        date = row['Date']
        
        # Merge provided coords with the built-in WC2026 coords
        all_coords = {**wc_2026_venues, **(venue_coordinates or {})}
        
        # Fallback to a central US coordinate if venue isn't mapped
        lat, lon = all_coords.get(venue, (39.8283, -98.5795))
        
        weather = fetch_weather_data(lat, lon, date)
        weather['Date'] = date
        weather[venue_col] = venue
        weather_records.append(weather)
        
    weather_df = pd.DataFrame(weather_records)
    
    # Merge back onto main df
    df = df.merge(weather_df, on=['Date', venue_col], how='left')
    
    return df

if __name__ == "__main__":
    print("Weather Features Module Loaded.")
