import json
from pathlib import Path
from urllib.parse import urljoin
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

SKIP_TEXT = {
    "back to dining locations",
    "advanced search",
    "nutrition",
    "allergens",
}


def is_recipe_link(href: str, text: str) -> bool:
    lower_text = text.lower().strip()
    lower_href = (href or "").lower().strip()

    if not lower_text or lower_text in SKIP_TEXT:
        return False
    if lower_text.startswith("[") and lower_text.endswith("]"):
        return False
    if "shortmenu.aspx" in lower_href or "dtdate=" in lower_href or "javascript:" in lower_href:
        return False

    # FoodPro dish links typically point to label.aspx or recipe detail pages
    return "label.aspx" in lower_href or "recipe" in lower_href or href != ""


def scrape_menu(url: str = MENU_URL) -> list[dict[str, str]]:
    res = requests.get(url, headers=HEADERS, timeout=15)
    res.raise_for_status()

    soup = BeautifulSoup(res.text, "html.parser")
    items: list[dict[str, str]] = []

    current_meal = "Unknown"
    current_station = "General"

    for row in soup.select("table tr"):
        meal_el = row.select_one(".shortmenumeals")
        if meal_el:
            meal_text = " ".join(meal_el.get_text(" ", strip=True).split())
            if meal_text:
                current_meal = meal_text
                current_station = "General"
            continue

        station_el = row.select_one(".shortmenucats")
        if station_el:
            raw_station = " ".join(station_el.get_text(" ", strip=True).split())
            cleaned_station = raw_station.strip("- ").strip()
            if cleaned_station:
                current_station = cleaned_station
            continue

        for link in row.select("a"):
            href = link.get("href", "")
            name = " ".join(link.get_text(" ", strip=True).split())
            if is_recipe_link(href, name):
                items.append({
                    "meal": current_meal,
                    "station": current_station,
                    "item": name,
                    "url": urljoin(url, href) if href else "",
                })

    return items


if __name__ == "__main__":
    output_path = Path("docs/menu.json")
    data = scrape_menu()

    if not data:
        print("Warning: 0 menu items found. Skipping write so existing docs/menu.json is preserved.")
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"count": len(data), "items": data}
        output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Wrote {len(data)} items to {output_path}")
