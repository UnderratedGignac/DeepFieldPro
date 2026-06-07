import json

with open("data/betarabia_api_responses.json", "r") as f:
    responses = json.load(f)

for i, resp in enumerate(responses):
    url = resp.get("url", "")
    data = resp.get("data", {})
    if not isinstance(data, dict):
        continue

    # Print only if events, odds, fixtures or markets is present
    interesting = [
        k
        for k in ["events", "odds", "fixtures", "markets", "fixture", "market"]
        if k in data
    ]
    if interesting:
        print(f"Index {i}: {url[:100]}")
        print(f"  Found keys: {interesting}")
        for key in interesting:
            val = data[key]
            if isinstance(val, dict):
                print(
                    f"    '{key}' is dict with {len(val)} items. Sample keys: {list(val.keys())[:5]}"
                )
            elif isinstance(val, list):
                print(
                    f"    '{key}' is list with {len(val)} items. Sample: {str(val[:1])[:200]}"
                )
            else:
                print(f"    '{key}' is {type(val)}")
