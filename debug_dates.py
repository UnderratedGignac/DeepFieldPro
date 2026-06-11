from seleniumbase import SB
import json
import datetime
import time

def check():
    for offset in [-1, 0, 1]:
        d = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=offset)
        today = d.strftime("%Y-%m-%d")
        url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{today}"
        print(f"Checking Date: {today} | URL: {url}")
        with SB(uc=True, headless=True) as sb:
            sb.open(url)
            time.sleep(2)
            content = sb.execute_script("return document.body.innerText;")
            try:
                data = json.loads(content)
                events = data.get("events", [])
                print(f"  Total events: {len(events)}")
            except Exception as e:
                print(f"  Error: {e}")

if __name__ == '__main__':
    check()
