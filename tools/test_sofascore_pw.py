"""Check stuck bets in Sofascore results."""
import asyncio, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import sys; sys.path.insert(0, "src")
from sofascore_results_scraper import _fetch_date_async

async def main():
    results = await _fetch_date_async("2026-06-17")
    print(f"Total finished: {len(results)}\n")

    targets = ["Utsiktens", "Atvidaberg", "Mochtas", "Lucan", "Goytacaz", "America RJ", "Brasil de Pelotas"]
    for t in targets:
        found = [k for k in results if t.lower() in k.lower()]
        if found:
            for k in found:
                print(f"FOUND: {k} -> {results[k]}")
        else:
            print(f"NOT FOUND: {t}")

asyncio.run(main())
