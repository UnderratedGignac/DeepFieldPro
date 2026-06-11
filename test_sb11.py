from seleniumbase import SB
from bs4 import BeautifulSoup
import json
with SB(uc=True, headless=True) as sb:
    sb.open('https://www.sofascore.com/football/match/dummy-slug/11352495')
    import time; time.sleep(5)
    html = sb.get_page_source()
    soup = BeautifulSoup(html, 'html.parser')
    scripts = soup.find_all('script')
    for s in scripts:
        if s.string and 'lineups' in s.string:
            print(s.string[:200])
            break
