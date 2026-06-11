from seleniumbase import SB
with SB(uc=True, headless=True) as sb:
    sb.open('https://www.sofascore.com/football/2026-06-11')
    import time; time.sleep(5)
    print([c for c in sb.driver.get_cookies() if 'cf' in c['name'].lower()])
    print('Now trying to fetch api...')
    c = sb.execute_script('''
        return fetch('https://api.sofascore.com/api/v1/sport/football/scheduled-events/2026-06-11').then(r=>r.json()).catch(e=>e.message);
    ''')
    print(c)
