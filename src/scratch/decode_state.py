import requests
import base64
import urllib.parse
import re
import json

print("Fetching Betarabia page...")
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
}
r = requests.get(
    "https://www.betarabia.com/sports/football", headers=headers, timeout=10
)

# Decode all atob expressions in script tags
atob_matches = re.findall(
    r'JSON\.parse\(decodeURIComponent\(atob\("([^"]+)"\)\)\)', r.text
)
print(f"Found {len(atob_matches)} base64-encoded blobs in script tags.")

for idx, blob in enumerate(atob_matches):
    try:
        decoded = urllib.parse.unquote(base64.b64decode(blob).decode("utf-8"))
        obj = json.loads(decoded)
        # Check what's inside
        keys = (
            list(obj.keys()) if isinstance(obj, dict) else f"list of length {len(obj)}"
        )
        print(f"Blob {idx}: {keys}")

        # Save to file
        with open(f"decoded_blob_{idx}.json", "w") as f:
            json.dump(obj, f, indent=2)

        # Search for "croatia" or "belgium" in the JSON string representation
        if "croatia" in decoded.lower() or "belgium" in decoded.lower():
            print(f"  --> Found Croatia or Belgium in Blob {idx}!")
    except Exception as e:
        print(f"Error decoding blob {idx}: {e}")
