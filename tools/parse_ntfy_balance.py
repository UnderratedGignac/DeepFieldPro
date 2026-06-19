"""Read user-sent messages from ntfy and parse any balance."""
import sys, os, requests, json, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

TOPIC = "deepfieldpro-elie-haddad"
OWN_TITLES = {"DeepField Hot Bets", "DeepField Setup Test", "DeepField Best Bet",
              "DeepField CRITICAL ERROR", "DeepField - Balance received", "DeepField"}

r = requests.get(f"https://ntfy.sh/{TOPIC}/json?poll=1&since=2h", timeout=10)
found = False
for line in r.text.strip().splitlines():
    msg = json.loads(line)
    if msg.get("title") in OWN_TITLES:
        continue
    text = (msg.get("message") or "").strip()
    nums = re.findall(r"\d+(?:\.\d+)?", text)
    if nums:
        balance = float(nums[0])
        print(f"User sent: '{text}' -> balance = ${balance:.2f}")
        found = True

if not found:
    print("No user balance messages found in last 2 hours.")
