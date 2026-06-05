from seleniumbase import SB
import json
import datetime
import time

def get_todays_fixtures_free():
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    url = f'https://api.sofascore.com/api/v1/sport/football/scheduled-events/{today}'
    
    with SB(uc=True, headless=True) as sb:
        sb.open(url)
        time.sleep(1) # Let Cloudflare bypass
        try:
            content = sb.execute_script('return document.body.innerText;')
            data = json.loads(content)
            events = data.get('events', [])
            
            # Format to match the old API structure for seamless integration
            formatted_fixtures = []
            for e in events:
                # Sofascore uses Unix timestamps
                kickoff_iso = datetime.datetime.fromtimestamp(e['startTimestamp'], datetime.timezone.utc).isoformat()
                
                status_code = 'NS'
                if e['status']['type'] == 'inprogress': status_code = '1H'
                elif e['status']['type'] == 'finished': status_code = 'FT'
                
                formatted_fixtures.append({
                    'fixture': {
                        'id': e['id'],
                        'date': kickoff_iso,
                        'status': {'short': status_code}
                    },
                    'league': {'name': e['tournament']['name']},
                    'teams': {
                        'home': {'name': e['homeTeam']['name']},
                        'away': {'name': e['awayTeam']['name']}
                    }
                })
            return formatted_fixtures
        except Exception as e:
            print(f"[!] Scraper Error (Fixtures): {e}")
            return []

def get_fixture_lineups_free(fixture_id):
    url = f'https://api.sofascore.com/api/v1/event/{fixture_id}/lineups'
    
    with SB(uc=True, headless=True) as sb:
        sb.open(url)
        time.sleep(1)
        try:
            content = sb.execute_script('return document.body.innerText;')
            data = json.loads(content)
            
            if 'home' not in data or 'away' not in data:
                return []
                
            # Map Sofascore lineups back to API-Football format
            home_xi = []
            for p in data['home'].get('players', []):
                if p.get('substitute') == False:
                    home_xi.append({'player': {'name': p['player']['name']}})
                    
            away_xi = []
            for p in data['away'].get('players', []):
                if p.get('substitute') == False:
                    away_xi.append({'player': {'name': p['player']['name']}})
                    
            return [
                {'startXI': home_xi},
                {'startXI': away_xi}
            ]
        except Exception as e:
            # Most likely 404 meaning lineups not released yet
            return []
