from seleniumbase import SB
import json
import time

def check_raw_html():
    url = "https://www.sofascore.com/"
    print(f"Checking URL: {url}")
    with SB(uc=True, headless=False) as sb:
        sb.open(url)
        print("Page opened. Waiting for content...")
        time.sleep(10) # Give it plenty of time to load matches
        
        # Try to find match names in the page
        try:
            # Common class for team names in Sofascore
            teams = sb.find_elements('div[class*="TeamName"]')
            if not teams:
                # Fallback to broader check
                content = sb.get_page_source()
                print(f"Content length: {len(content)}")
                if "No events" in content:
                    print("Page explicitly says 'No events'")
                else:
                    print("Found no team names, but page content exists.")
            else:
                print(f"Found {len(teams)} team elements on page.")
                for t in teams[:10]:
                    print(f"- {t.text}")
        except Exception as e:
            print(f"Error checking elements: {e}")

if __name__ == '__main__':
    check_raw_html()
