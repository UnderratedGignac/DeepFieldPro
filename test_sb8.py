from seleniumbase import SB
with SB(uc=True, headless=True) as sb:
    sb.open('https://www.sofascore.com/football/2026-06-11')
    import time; time.sleep(5)
    html = sb.get_page_source()
    print('match' in html.lower())
    print('venezuela' in html.lower())
