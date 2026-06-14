import json

with open("data/betarabia_api_responses.json", "r") as f:
    responses = json.load(f)

for i, resp in enumerate(responses):
    data = resp.get("data", {})
    if (
        isinstance(data, dict)
        and "events" in data
        and isinstance(data["events"], list)
        and len(data["events"]) > 0
    ):
        event = data["events"][0]
        print("Keys of event:", list(event.keys()))
        main_odds = event.get("main_odds", {})
        print("Keys of main_odds:", list(main_odds.keys()))
        for k, v in main_odds.items():
            if isinstance(v, dict):
                print(f"  Sub-keys in '{k}': {list(v.keys())[:3]}")
                # Print a sample of items in this sub-key
                first_item_key = list(v.keys())[0] if v else None
                if first_item_key:
                    print(f"    Sample item in '{k}': {v[first_item_key]}")
        break
