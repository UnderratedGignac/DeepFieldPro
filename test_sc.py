import traceback
from src.free_scraper_module import get_todays_fixtures_free
try:
    res = get_todays_fixtures_free()
    print('Length:', len(res))
except Exception as e:
    traceback.print_exc()
