import json
from pathlib import Path
import requests
from bs4 import BeautifulSoup

MENU_URL = (
    "https://foodpro.ucr.edu/foodpro/shortmenu.aspx"
    "?sName=University%20of%20California%2C%20Riverside%20Dining%20Services"
    "&locationNum=03&locationName=Glasgow&naFlag=1"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; UCRMenuBot/1.0)"
}


def scrape_menu() -> list[dict[str, str]]:
    res = requests.get(MENU_URL, headers=HEADERS, timeout=15)
    res.raise_for_status()

    soup = BeautifulSoup(res.text, "html.parser")
    items: list[dict[str, str]] = []

    current_meal = "Unknown"
    current_station = "General"

    for row in soup.select("table tr"):
        meal_el = row.select_one(".shortmenumeals")
        if meal_el:
            current_meal = " ".join(meal_el.get_text(" ", strip=True).split())
            continue

        station_el = row.select_one(".shortmenucats")
        if station_el:
            raw_station = " ".join(station_el.get_text(" ", strip=True).split())
            current_station = raw_station.strip("- ").strip()
            continue

        for link in row.select("a"):
            name = " ".join(link.get_text(" ", strip=True).split())
            if name and name.lower() not in {"back to dining locations", "advanced search"}:
                items.append({
                    "meal": current_meal,
                    "station": current_station,
                    "item": name,
                })

    return items


if __name__ == "__main__":
    output_path = Path("docs/menu.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = scrape_menu()
    output_path.write_text(json.dumps({"count": len(data), "items": data}, indent=2), encoding="utf-8")
    print(f"Wrote {len(data)} items to {output_path}")
