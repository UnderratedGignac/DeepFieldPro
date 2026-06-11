from seleniumbase import SB
import json
import time

def check_live():
    url = "https://api.sofascore.com/api/v1/sport/football/events/live"
    print(f"Checking URL: {url}")
    with SB(uc=True, headless=True) as sb:
        sb.open(url)
        time.sleep(2)
        content = sb.execute_script("return document.body.innerText;")
        try:
            data = json.loads(content)
            events = data.get("events", [])
            print(f"Total live events found: {len(events)}")
            for e in events[:5]:
                print(f"- {e['homeTeam']['name']} vs {e['awayTeam']['name']}")
        except Exception as e:
            print(f"Error parsing JSON: {e}")

if __name__ == '__main__':
    check_live()
