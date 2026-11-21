"""Menu recommendation algorithm for UCR Dining Finder.

This is the original script turned into importable functions. The SCORING RULES ARE
UNCHANGED from the original Taste_Checker:

    +1  spice  within 2 of the dish   (abs(difference) < 3)
    +1  sweet  within 2 of the dish
    +1  savory within 2 of the dish
    +1  cuisine matches
    +10 meal matches

Formats (see menudox.txt):

    Menu file   one record per ':' ->  Food-Spice-Sweet-Savor-Cuisine-Meal-Location-:
                e.g.  Pad Thai Noodles-3-5-7-asian-Lunch-L-:
                file name: MM-DD-YYYY-MENU.txt   (e.g. 11-21-2026-MENU.txt)

    Profile     Spice-Sweet-Savor-Cuisine-Meal-      (note the trailing '-')
                e.g.  "7-5-6-asian-Lunch-"
"""
import logging
from pathlib import Path

log = logging.getLogger(__name__)

MENU_DIR = Path(__file__).resolve().parent / "txt4algo"

MEALS = ("Breakfast", "Lunch", "Dinner")
HALLS = {"G": "Glasgow", "L": "Lothian"}

TASTE_TOLERANCE = 3        # original rule: abs(difference) < 3
MEAL_BONUS = 10
MAX_TASTE_POINTS = 4       # 3 tastes + 1 cuisine (what "100% match" means)


# ---------------------------------------------------------------- menu files

def menu_path_for(day, menu_dir=MENU_DIR):
    """Path of the menu file for a datetime.date, e.g. txt4algo/11-21-2026-MENU.txt."""
    return Path(menu_dir) / f"{day:%m-%d-%Y}-MENU.txt"


def load_menu(path):
    """Parse a menu file into a list of dicts. Raises FileNotFoundError if it's missing.

    Malformed records are skipped (and logged) instead of crashing the site.
    """
    text = Path(path).read_text(encoding="utf8")
    items = []
    for record in text.split(":"):
        record = record.strip()
        if not record:
            continue
        # rsplit from the right so a dish name containing '-' still parses
        parts = record.rstrip("-").rsplit("-", 6)
        try:
            if len(parts) != 7:
                raise ValueError("expected 7 fields")
            name, spice, sweet, savory, cuisine, meal, loc = (p.strip() for p in parts)
            if meal not in MEALS:
                raise ValueError(f"unknown meal {meal!r}")
            if loc not in HALLS:
                raise ValueError(f"unknown location {loc!r}")
            if not name or not cuisine:
                raise ValueError("empty name or cuisine")
            items.append({
                "name": name,
                "spice": int(spice),
                "sweet": int(sweet),
                "savory": int(savory),
                "cuisine": cuisine.lower(),
                "meal": meal,
                "location": loc,
            })
        except ValueError as err:
            log.warning("Skipping malformed menu record in %s: %r (%s)",
                        Path(path).name, record, err)
    return items


# ------------------------------------------------------------------ profiles

def build_profile(spice, sweet, savory, cuisine, meal):
    """Build the profile string the algorithm expects: 'Spice-Sweet-Savor-Cuisine-Meal-'."""
    return f"{int(spice)}-{int(sweet)}-{int(savory)}-{cuisine}-{meal}-"


def _parse_profile(profile):
    spice, sweet, savory, cuisine, meal = profile.rstrip("-").split("-")
    return int(spice), int(sweet), int(savory), cuisine, meal


def score_item(profile, item):
    """Points for one dish against one profile string (the original Taste_Checker rules)."""
    spice, sweet, savory, cuisine, meal = _parse_profile(profile)
    points = 0
    if abs(spice - item["spice"]) < TASTE_TOLERANCE:
        points += 1
    if abs(sweet - item["sweet"]) < TASTE_TOLERANCE:
        points += 1
    if abs(savory - item["savory"]) < TASTE_TOLERANCE:
        points += 1
    if cuisine == item["cuisine"]:
        points += 1
    if meal == item["meal"]:
        points += MEAL_BONUS
    return points


# ------------------------------------------------------------------- ranking

def rank_menu(items, profiles):
    """Score every item and return them best-first.

    `profiles` is a list of profile strings. The profile format holds ONE cuisine but the
    quiz saves two or more, so the caller passes one string per liked cuisine and each
    dish keeps its best score (so it gets the cuisine point if it matches ANY of them).

    Sorted by points (high to low). Ties are broken by how close the dish is to the user's
    exact spice/sweet/savory numbers, then by name, so the order is stable.
    """
    spice, sweet, savory, _, _ = _parse_profile(profiles[0])
    ranked = []
    for item in items:
        points = max(score_item(p, item) for p in profiles)
        distance = (abs(spice - item["spice"]) + abs(sweet - item["sweet"])
                    + abs(savory - item["savory"]))
        ranked.append({
            **item,
            "dining_hall": HALLS[item["location"]],
            "points": points,
            "distance": distance,
        })
    ranked.sort(key=lambda d: (-d["points"], d["distance"], d["name"]))
    return ranked


def recommend(menu_path, quiz, meal, limit=None):
    """Ranked dishes for one meal from one menu file.

    quiz: the dict from init_db.get_latest_result -> {"spice", "sweet", "savory", "cuisines"}
    meal: "Breakfast", "Lunch" or "Dinner"
    Each result has name, cuisine, meal, location ('G'/'L'), dining_hall, points, match (0-100).
    Returns [] if the menu has no dishes for that meal. Raises FileNotFoundError for no menu.
    """
    items = [i for i in load_menu(menu_path) if i["meal"] == meal]
    if not items:
        return []

    cuisines = quiz.get("cuisines") or ["none"]
    profiles = [
        build_profile(quiz["spice"], quiz["sweet"], quiz["savory"], c, meal)
        for c in cuisines
    ]

    seen, results = set(), []
    for dish in rank_menu(items, profiles):
        key = (dish["name"], dish["location"])
        if key in seen:
            continue
        seen.add(key)
        dish["match"] = round((dish["points"] - MEAL_BONUS) / MAX_TASTE_POINTS * 100)
        results.append(dish)

    return results[:limit] if limit else results


if __name__ == "__main__":
    # Quick manual test:  python algorithm.py
    from datetime import date
    demo_quiz = {"spice": 0, "sweet": 2, "savory": 7, "cuisines": ["italian"]}
    path = menu_path_for(date(2026, 11, 21))
    print(f"Top Lunch picks from {path.name}:")
    for d in recommend(path, demo_quiz, "Lunch", limit=5):
        print(f"  {d['match']:>3}%  {d['name']}  ({d['dining_hall']})")
