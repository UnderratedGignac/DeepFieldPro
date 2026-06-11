from seleniumbase import SB
with SB(uc=True, headless=True) as sb:
    sb.uc_open_with_reconnect('https://api.sofascore.com/api/v1/sport/football/scheduled-events/2026-06-11', 5)
    print(sb.get_page_source()[:500])
