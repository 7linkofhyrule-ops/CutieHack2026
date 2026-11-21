from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

MENU_URL = (
    "https://foodpro.ucr.edu/foodpro/shortmenu.aspx"
    "?sName=University%20of%20California%2C%20Riverside%20Dining%20Services"
    "&locationNum=03&locationName=Glasgow&naFlag=1"
)

OUTPUT_TXT = Path("glasgow_menu.txt")

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

    return "label.aspx" in lower_href or "recipe" in lower_href or href != ""


def scrape_menu(url: str = MENU_URL) -> list[dict[str, str]]:
    response = requests.get(url, headers=HEADERS, timeout=15)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
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


def save_to_txt(items: list[dict[str, str]], filepath: Path = OUTPUT_TXT) -> None:
    lines = [
        f"{entry['item']} | {entry['meal']} | {entry['station']} | {entry['url']}"
        for entry in items
    ]
    filepath.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


if __name__ == "__main__":
    menu_items = scrape_menu()
    save_to_txt(menu_items, OUTPUT_TXT)
    print(f"Saved {len(menu_items)} items to {OUTPUT_TXT}")
