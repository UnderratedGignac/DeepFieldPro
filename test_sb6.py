from seleniumbase import SB
with SB(uc=True, headless=True) as sb:
    sb.open('https://www.sofascore.com/football')
    import time; time.sleep(5)
    print(sb.get_page_source()[:500])
