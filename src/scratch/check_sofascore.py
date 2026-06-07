import sys
import os

sys.path.insert(0, os.path.dirname(__file__) + "/..")
from free_scraper_module import get_todays_fixtures_free

fixtures = get_todays_fixtures_free()
print(f"Total fixtures: {len(fixtures)}")
finished = [f for f in fixtures if f['fixture']['status']['short'] == 'FT']
print(f"Finished fixtures count: {len(finished)}")
for f in finished[:10]:
    home = f['teams']['home']['name']
    away = f['teams']['away']['name']
    h_score = f['fixture']['home_score']
    a_score = f['fixture']['away_score']
    print(f"  FT: {home} {h_score} - {a_score} {away}")
    
not_started = [f for f in fixtures if f['fixture']['status']['short'] == 'NS']
print(f"Not started fixtures count: {len(not_started)}")
for f in not_started[:5]:
    home = f['teams']['home']['name']
    away = f['teams']['away']['name']
    print(f"  NS: {home} vs {away} at {f['fixture']['date']}")
