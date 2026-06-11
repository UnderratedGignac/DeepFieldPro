from seleniumbase import SB
with SB(headless=True) as sb:
    sb.open('https://api.sofascore.com/api/v1/sport/football/scheduled-events/2026-06-11')
    print(sb.get_page_source()[:500])
