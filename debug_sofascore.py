from seleniumbase import SB
import json
import datetime
import time

def check():
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{today}"
    print(f"Checking URL: {url}")
    with SB(uc=True, headless=True) as sb:
        sb.open(url)
        time.sleep(2)
        content = sb.execute_script("return document.body.innerText;")
        try:
            data = json.loads(content)
            events = data.get("events", [])
            print(f"Total events found: {len(events)}")
            for e in events[:5]:
                print(f"- {e['homeTeam']['name']} vs {e['awayTeam']['name']} @ {e['startTimestamp']}")
            
            # Look for MAS de Fes
            for e in events:
                if "Fès" in e['homeTeam']['name'] or "Fès" in e['awayTeam']['name']:
                    print(f"FOUND MATCH: {e['homeTeam']['name']} vs {e['awayTeam']['name']} @ {e['startTimestamp']}")
        except Exception as e:
            print(f"Error parsing JSON: {e}")
            print("Content was:")
            print(content[:500])

if __name__ == '__main__':
    check()
