"""Menu recommendation algorithm for UCR Dining Finder.

Pipeline for one meal:   menu file -> dedupe -> FILTER by restrictions -> RANK by taste

Scoring rules (ranking only, unchanged from the original Taste_Checker):

    +1  spice  within 2 of the dish   (abs(difference) < 3)
    +1  sweet  within 2 of the dish
    +1  savory within 2 of the dish
    +1  cuisine matches
    +10 meal matches

FORMATS
-------
Menu file (see menudox.txt) - one record per ':'

    Food-Spice-Sweet-Savor-Cuisine-Meal-Location-:             legacy: dietary info UNKNOWN
    Food-Spice-Sweet-Savor-Cuisine-Meal-Location-Flags-:       with dietary info

    Flags = legend codes joined by '+', e.g.  vegetarian+milk+wheat
            'none'    -> the menu was checked and lists no legend icons for this dish
            'unknown' -> dietary info could not be read (same as leaving the field out)
    File name: MM-DD-YYYY-MENU.txt   (e.g. 11-21-2026-MENU.txt)

Profile string (one per liked cuisine)

    Spice-Sweet-Savor-Cuisine-Meal-                 no restrictions (identical to the old format)
    Spice-Sweet-Savor-Cuisine-Meal-Restrictions-    e.g. 7-5-6-asian-Lunch-vegan+peanuts-

SAFETY RULES (restrictions are hard filters, never score adjustments)
    * A dish whose flags include an allergen the user avoids is removed.
    * A dish that can't prove a required diet (Vegan / Vegetarian / Gluten Free) is removed.
    * A dish with UNKNOWN dietary info is removed whenever the user has ANY restriction.
    * Missing information is never read as "safe".
"""
import logging
from collections import Counter
from pathlib import Path

log = logging.getLogger(__name__)

MENU_DIR = Path(__file__).resolve().parent / "txt4algo"

MEALS = ("Breakfast", "Lunch", "Dinner")
HALLS = {"G": "Glasgow", "L": "Lothian"}

TASTE_TOLERANCE = 3        # original rule: abs(difference) < 3
MEAL_BONUS = 10
MAX_TASTE_POINTS = 4       # 3 tastes + 1 cuisine (what "100% match" means)


# ------------------------------------------------------------ dietary legend
# The 12 entries of the dining-hall menu legend, in legend order, with the exact
# legend wording as `label`. `code` is what we store in the database, the menu
# files and the profile string (so it must never contain '-', ':' or '+').
#   kind "diet"     -> a requirement the dish must MEET (Vegan, Vegetarian, Gluten Free)
#   kind "allergen" -> a "Contains ..." icon; the user can say they must AVOID it
LEGEND = (
    {"code": "vegan",       "kind": "diet",     "label": "Vegan"},
    {"code": "vegetarian",  "kind": "diet",     "label": "Vegetarian"},
    {"code": "gluten_free", "kind": "diet",     "label": "Gluten Free"},
    {"code": "milk",        "kind": "allergen", "label": "Contains Milk"},
    {"code": "eggs",        "kind": "allergen", "label": "Contains Eggs"},
    {"code": "fish",        "kind": "allergen", "label": "Contains Fish"},
    {"code": "shellfish",   "kind": "allergen", "label": "Contains Crustacean Shellfish"},
    {"code": "tree_nuts",   "kind": "allergen", "label": "Contains Tree Nuts"},
    {"code": "peanuts",     "kind": "allergen", "label": "Contains Peanuts"},
    {"code": "wheat",       "kind": "allergen", "label": "Contains Wheat"},
    {"code": "soy",         "kind": "allergen", "label": "Contains Soybeans"},
    {"code": "sesame",      "kind": "allergen", "label": "Contains Sesame"},
)

LEGEND_CODES = tuple(item["code"] for item in LEGEND)
LEGEND_LABELS = {item["code"]: item["label"] for item in LEGEND}
DIET_CODES = frozenset(i["code"] for i in LEGEND if i["kind"] == "diet")
ALLERGEN_CODES = frozenset(i["code"] for i in LEGEND if i["kind"] == "allergen")
_CODE_BY_LABEL = {item["label"].lower(): item["code"] for item in LEGEND}

# If the data says a dish is Vegan/Vegetarian/Gluten Free AND ALSO carries one of these
# icons, the data contradicts itself, so we refuse to trust the diet claim.
_CONFLICTS = {
    "vegan": frozenset({"milk", "eggs", "fish", "shellfish"}),
    "vegetarian": frozenset({"fish", "shellfish"}),
    "gluten_free": frozenset({"wheat"}),
}


def normalize_restrictions(codes):
    """Validate legend codes; return them de-duplicated, in legend order.

    Raises ValueError for anything that isn't a legend code (we never silently drop
    a restriction the person asked for).
    """
    codes = set(codes or ())
    bad = sorted(codes - set(LEGEND_CODES))
    if bad:
        raise ValueError(f"unknown dietary option(s): {bad}")
    return tuple(c for c in LEGEND_CODES if c in codes)


def flags_from_labels(labels):
    """Exact legend labels (e.g. ['Vegan', 'Contains Milk']) -> frozenset of codes.

    For the scraper: feed it the icon names read from a dish. Raises ValueError for text
    that isn't one of the 12 legend labels, so the scraper can decide to store 'unknown'
    rather than guess.
    """
    codes = set()
    for label in labels:
        key = " ".join(str(label).split()).lower()
        if key not in _CODE_BY_LABEL:
            raise ValueError(f"not a legend label: {label!r}")
        codes.add(_CODE_BY_LABEL[key])
    return frozenset(codes)


def parse_flags(token):
    """Flags field of a menu record -> frozenset of codes, or None if unknown."""
    token = token.strip().lower()
    if token in ("", "unknown"):
        return None
    if token == "none":
        return frozenset()
    codes = token.split("+")
    bad = [c for c in codes if c not in LEGEND_CODES]
    if bad:
        raise ValueError(f"unknown dietary code(s) {bad}")
    return frozenset(codes)


def format_flags(flags):
    """Inverse of parse_flags: None -> 'unknown', empty -> 'none', else codes in legend order."""
    if flags is None:
        return "unknown"
    if not flags:
        return "none"
    return "+".join(c for c in LEGEND_CODES if c in flags)


def dietary_view(flags):
    """What a template needs to show a dish's dietary info."""
    if flags is None:
        return {"dietary_known": False, "diet_labels": [], "contains_labels": []}
    return {
        "dietary_known": True,
        "diet_labels": [LEGEND_LABELS[c] for c in LEGEND_CODES if c in flags and c in DIET_CODES],
        "contains_labels": [LEGEND_LABELS[c] for c in LEGEND_CODES
                            if c in flags and c in ALLERGEN_CODES],
    }


# ---------------------------------------------------------------- menu files

def menu_path_for(day, menu_dir=MENU_DIR):
    """Path of the menu file for a datetime.date, e.g. txt4algo/11-21-2026-MENU.txt."""
    return Path(menu_dir) / f"{day:%m-%d-%Y}-MENU.txt"


def format_menu_record(name, spice, sweet, savory, cuisine, meal, location, flags):
    """Build one menu-file record (including the trailing '-:'). For the scraper to call.

    flags: frozenset/set of legend codes, an empty set for 'checked, nothing listed',
           or None when the dietary info could not be read.
    """
    if ":" in name:
        raise ValueError(f"':' is the record separator and can't be in a dish name: {name!r}")
    if meal not in MEALS or location not in HALLS:
        raise ValueError(f"bad meal/location: {meal!r}, {location!r}")
    if not cuisine or "-" in cuisine or ":" in cuisine:
        raise ValueError(f"bad cuisine: {cuisine!r}")
    if flags is not None:
        normalize_restrictions(flags)          # raises on anything outside the legend
    return (f"{name}-{int(spice)}-{int(sweet)}-{int(savory)}-{cuisine.lower()}-"
            f"{meal}-{location}-{format_flags(flags)}-:")


def load_menu(path):
    """Parse a menu file into a list of dicts. Raises FileNotFoundError if it's missing.

    Each dict has name, spice, sweet, savory, cuisine, meal, location and `flags`
    (a frozenset of legend codes, or None when the record carries no dietary info).
    Malformed records are skipped (and logged) instead of crashing the site; skipping a
    dish can never put anyone at risk.
    """
    text = Path(path).read_text(encoding="utf8")
    items = []
    for record in text.split(":"):
        record = record.strip()
        if not record:
            continue
        try:
            tokens = record.rstrip("-").split("-")
            # A legacy record ends in the location (G/L). Otherwise the last token is the
            # flags field. (A flags token can never be exactly 'G' or 'L'.)
            if tokens[-1] in HALLS:
                flags = None
            else:
                flags = parse_flags(tokens.pop())
            # rsplit from the right so a dish name containing '-' still parses
            parts = "-".join(tokens).rsplit("-", 6)
            if len(parts) != 7:
                raise ValueError("expected 7 fields before the dietary flags")
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
                "flags": flags,
            })
        except ValueError as err:
            log.warning("Skipping malformed menu record in %s: %r (%s)",
                        Path(path).name, record, err)
    return items


# ------------------------------------------------------------------ profiles

def build_profile(spice, sweet, savory, cuisine, meal, restrictions=()):
    """Profile string: 'Spice-Sweet-Savor-Cuisine-Meal-' plus 'Restrictions-' when there are any."""
    profile = f"{int(spice)}-{int(sweet)}-{int(savory)}-{cuisine}-{meal}-"
    restrictions = normalize_restrictions(restrictions)
    if restrictions:
        profile += "+".join(restrictions) + "-"
    return profile


def _parse_profile(profile):
    """-> (spice, sweet, savory, cuisine, meal, restrictions frozenset). Accepts old 5-field strings."""
    fields = profile.rstrip("-").split("-")
    if len(fields) not in (5, 6):
        raise ValueError(f"bad profile string: {profile!r}")
    spice, sweet, savory, cuisine, meal = fields[:5]
    restrictions = frozenset(normalize_restrictions(fields[5].split("+"))) if len(fields) == 6 \
        else frozenset()
    return int(spice), int(sweet), int(savory), cuisine, meal, restrictions


def score_item(profile, item):
    """Taste points for one dish against one profile string (the original Taste_Checker rules)."""
    spice, sweet, savory, cuisine, meal, _ = _parse_profile(profile)
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


# ----------------------------------------------------------------- filtering

def check_restrictions(item, restrictions):
    """None if the dish is eligible, else (kind, [labels]) explaining why it is removed.

    kind: 'unknown'  no dietary info, so we can't confirm anything
          'allergen' the dish carries an icon the user must avoid
          'diet'     the dish can't prove a required diet (or its data contradicts itself)
    """
    if not restrictions:
        return None                      # nothing to protect, so nothing to confirm
    flags = item["flags"]
    if flags is None:
        return ("unknown", [])

    hits = [LEGEND_LABELS[c] for c in LEGEND_CODES
            if c in restrictions and c in ALLERGEN_CODES and c in flags]
    if hits:
        return ("allergen", hits)

    failed = []
    for need in ("vegan", "vegetarian", "gluten_free"):
        if need not in restrictions:
            continue
        # Vegan dishes also satisfy "Vegetarian" (vegan is the stricter label).
        ok = need in flags or (need == "vegetarian" and "vegan" in flags)
        if not ok or flags & _CONFLICTS[need]:
            failed.append(LEGEND_LABELS[need])
    if failed:
        return ("diet", failed)
    return None


def filter_menu(items, restrictions):
    """Split dishes into (eligible, excluded). excluded is a list of (item, kind, labels)."""
    restrictions = frozenset(normalize_restrictions(restrictions))
    eligible, excluded = [], []
    for item in items:
        problem = check_restrictions(item, restrictions)
        if problem is None:
            eligible.append(item)
        else:
            excluded.append((item, problem[0], problem[1]))
    return eligible, excluded


# ------------------------------------------------------------------- ranking

def rank_menu(items, profiles):
    """Remove dishes the profile forbids, then score the rest, best-first.

    `profiles` is a list of profile strings. The profile format holds ONE cuisine but the
    quiz saves two or more, so the caller passes one string per liked cuisine and each
    dish keeps its best score (so it gets the cuisine point if it matches ANY of them).
    All profiles carry the same restrictions.

    Restrictions are enforced here too, so ranking can never surface a forbidden dish
    even if this function is called directly. Taste only orders the survivors.

    Sorted by points (high to low). Ties are broken by how close the dish is to the user's
    exact spice/sweet/savory numbers, then by name, so the order is stable.
    """
    spice, sweet, savory, _, _, restrictions = _parse_profile(profiles[0])
    eligible, _ = filter_menu(items, restrictions)
    ranked = []
    for item in eligible:
        points = max(score_item(p, item) for p in profiles)
        distance = (abs(spice - item["spice"]) + abs(sweet - item["sweet"])
                    + abs(savory - item["savory"]))
        ranked.append({
            **item,
            **dietary_view(item["flags"]),
            "dining_hall": HALLS[item["location"]],
            "points": points,
            "distance": distance,
        })
    ranked.sort(key=lambda d: (-d["points"], d["distance"], d["name"]))
    return ranked


def recommend_detailed(menu_path, quiz, meal, limit=None):
    """Ranked, restriction-safe dishes for one meal, plus a report of what was hidden.

    quiz: {"spice", "sweet", "savory", "cuisines", "restrictions"}  ("restrictions" optional;
          None or missing means no restrictions)
    Returns {"dishes": [...], "total": n, "hidden": {"allergen": n, "diet": n, "unknown": n},
             "hidden_total": n}
    Each dish has name, cuisine, meal, location ('G'/'L'), dining_hall, match (0-100), flags,
    dietary_known, diet_labels, contains_labels.
    Raises FileNotFoundError when there is no menu file; total == 0 means no dishes that meal.
    """
    seen, items = set(), []
    for item in load_menu(menu_path):
        key = (item["name"], item["location"])
        if item["meal"] == meal and key not in seen:
            seen.add(key)
            items.append(item)

    restrictions = normalize_restrictions(quiz.get("restrictions"))
    cuisines = quiz.get("cuisines") or ["none"]
    profiles = [
        build_profile(quiz["spice"], quiz["sweet"], quiz["savory"], c, meal, restrictions)
        for c in cuisines
    ] 

    _, excluded = filter_menu(items, restrictions)
    hidden = Counter(kind for _, kind, _ in excluded)

    dishes = rank_menu(items, profiles) if items else []
    for dish in dishes:
        dish["match"] = round((dish["points"] - MEAL_BONUS) / MAX_TASTE_POINTS * 100)

    return {
        "dishes": dishes[:limit] if limit else dishes,
        "total": len(items),
        "hidden": {k: hidden.get(k, 0) for k in ("allergen", "diet", "unknown")},
        "hidden_total": len(excluded),
    }


def recommend(menu_path, quiz, meal, limit=None):
    """Just the ranked dish list from recommend_detailed()."""
    return recommend_detailed(menu_path, quiz, meal, limit)["dishes"]


if __name__ == "__main__":
    # Quick manual test:  python algorithm.py
    from datetime import date
    demo_quiz = {"spice": 0, "sweet": 2, "savory": 7, "cuisines": ["italian"],
                 "restrictions": ["peanuts"]}
    path = menu_path_for(date(2026, 11, 21))
    report = recommend_detailed(path, demo_quiz, "Lunch", limit=5)
    print(f"{path.name}: {report['total']} Lunch dishes, hidden: {report['hidden']}")
    for d in report["dishes"]:
        print(f"  {d['match']:>3}%  {d['name']}  ({d['dining_hall']})")
