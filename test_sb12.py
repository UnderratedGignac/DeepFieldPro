from seleniumbase import SB
from bs4 import BeautifulSoup
with SB(uc=True, headless=True) as sb:
    sb.open('https://www.sofascore.com/football/2026-06-11')
    import time; time.sleep(5)
    html = sb.get_page_source()
    print('venezuela' in html.lower())
    for line in html.split('\n'):
        if 'venezuela' in line.lower():
            print(line[:300])
