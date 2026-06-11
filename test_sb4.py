from seleniumbase import SB
with SB(uc=True, headless=True) as sb:
    sb.open("https://www.sofascore.com/football")
    import time
    time.sleep(3)
    script = """
    var callback = arguments[arguments.length - 1];
    fetch("https://api.sofascore.com/api/v1/sport/football/scheduled-events/2026-06-11")
        .then(r => r.text())
        .then(t => callback(t));
    """
    res = sb.execute_async_script(script)
    print(res[:200])
