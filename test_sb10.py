from seleniumbase import SB
from bs4 import BeautifulSoup
import json
with SB(uc=True, headless=True) as sb:
    sb.open('https://www.sofascore.com/football/2026-06-11')
    import time; time.sleep(5)
    html = sb.get_page_source()
    soup = BeautifulSoup(html, 'html.parser')
    scripts = soup.find_all('script')
    for s in scripts:
        if s.string and 'events' in s.string and 'tournament' in s.string:
            data = json.loads(s.string)
            events = data['props']['pageProps'].get('events', [])
            if not events:
                # Sometimes it's inside another nested object
                events = data['props']['pageProps'].get('initialEvents', {}).get('events', [])
            print('Found events:', len(events))
            break
