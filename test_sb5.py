from seleniumbase import SB
with SB(uc=True, headless2=True) as sb:
    sb.open('https://api.sofascore.com/api/v1/sport/football/scheduled-events/2026-06-11')
    import time; time.sleep(2)
    print(sb.get_page_source()[:500])
