import os
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import redirect, render_template, request, session, url_for

import algorithm
import init_db as db

LA = ZoneInfo("America/Los_Angeles")

MEALS = algorithm.MEALS          # ("Breakfast", "Lunch", "Dinner")
DISHES_SHOWN = 8


def today_la():
    """Today's date in Los Angeles, no matter where the server runs."""
    return datetime.now(LA).date()


def get_profile():
    """Latest quiz answers for this browser, shaped for the dashboard. None if no quiz yet."""
    user = db.get_user_by_token(session.get("user_token"))
    if user is None:
        return None

    result = db.get_latest_result(user["id"])
    if result is None:
        return None

    db.touch_user(user["id"])   # records last_seen

    return {
        "spicy": result["spice"],
        "sweet": result["sweet"],
        "savory": result["savory"],
        "cuisines": result["cuisines"],
        # None = quiz taken before the dietary section existed (never asked)
        "restrictions": result["restrictions"],
    }


def _join(parts):
    """['a', 'b', 'c'] -> 'a, b and c'"""
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def hidden_summary(hidden):
    """Plain-English reasons dishes were hidden, e.g. '2 contain an allergen you avoid and 5 ...'."""
    def phrase(count, one, many):
        return f"{count} {one if count == 1 else many}"

    parts = []
    if hidden["allergen"]:
        parts.append(phrase(hidden["allergen"], "contains an allergen you avoid",
                            "contain an allergen you avoid"))
    if hidden["diet"]:
        parts.append(phrase(hidden["diet"], "doesn't meet your dietary requirements",
                            "don't meet your dietary requirements"))
    if hidden["unknown"]:
        parts.append(phrase(hidden["unknown"], "has no dietary info, so we can't confirm it",
                            "have no dietary info, so we can't confirm them"))
    return _join(parts) if parts else ""


def menu_for(day, meal, profile):
    """Everything the dashboard needs for one day + meal.

    Returns a dict: dishes, empty_title, empty_message, hidden_total, hidden_summary.
    """
    # TESTING ONLY: DINING_MENU_FILE=path/to/file.txt makes every day use that one menu file
    # (used with demo_menus/ to try dietary filtering before the scraper emits dietary data).
    path = os.environ.get("DINING_MENU_FILE") or algorithm.menu_path_for(day)

    # The algorithm reads the quiz in its own key names (spice, not spicy)
    quiz = {
        "spice": profile["spicy"],
        "sweet": profile["sweet"],
        "savory": profile["savory"],
        "cuisines": profile["cuisines"],
        "restrictions": profile["restrictions"] or [],
    }

    result = {"dishes": [], "empty_title": "", "empty_message": "",
              "hidden_total": 0, "hidden_summary": ""}

    try:
        report = algorithm.recommend_detailed(path, quiz, meal, limit=DISHES_SHOWN)
    except FileNotFoundError:
        result.update(
            empty_title="Today's menu isn't available yet",
            empty_message="We don't have a Glasgow or Lothian menu loaded for today. "
                          "Check the official dining menus in the meantime.",
        )
        return result

    result["dishes"] = report["dishes"]
    result["hidden_total"] = report["hidden_total"]
    result["hidden_summary"] = hidden_summary(report["hidden"])

    if report["total"] == 0:
        result.update(
            empty_title=f"No {meal.lower()} menu today",
            empty_message=f"Glasgow and Lothian aren't listing any {meal.lower()} items for today. "
                          "Try another meal above.",
        )
    elif not report["dishes"]:
        # There ARE dishes, but every one was removed by the person's dietary rules.
        result.update(
            empty_title=f"Nothing matches your dietary needs for {meal.lower()}",
            empty_message=(
                f"Glasgow and Lothian list {report['total']} {meal.lower()} "
                f"{'dish' if report['total'] == 1 else 'dishes'} today, but we hid "
                f"{'it' if report['total'] == 1 else 'all of them'}: {result['hidden_summary']}. "
                "Try another meal, or update your dietary needs by retaking the quiz."
            ),
        )
    return result


def homepage_response():
    profile = get_profile()

    # New visitors (or anyone who hasn't finished the quiz) see the welcome page + quiz button
    if profile is None:
        return render_template("welcome.html")

    today = today_la()

    meal = request.args.get("meal", "Lunch").title()
    if meal not in MEALS:
        meal = "Lunch"

    menu = menu_for(today, meal, profile)
    restrictions = profile["restrictions"] or []

    return render_template(
        "dashboard.html",
        today_label=f"{today:%A, %B} {today.day}",
        meal=meal,
        meals=MEALS,
        profile=profile,
        dishes=menu["dishes"],
        empty_title=menu["empty_title"],
        empty_message=menu["empty_message"],
        hidden_total=menu["hidden_total"],
        hidden_summary=menu["hidden_summary"],
        # None -> the quiz predates the dietary section; [] -> answered, no restrictions
        restrictions_asked=profile["restrictions"] is not None,
        restrictions=restrictions,
        diet_needs=[algorithm.LEGEND_LABELS[c] for c in restrictions
                    if c in algorithm.DIET_CODES],
        allergens_avoided=[algorithm.LEGEND_LABELS[c] for c in restrictions
                           if c in algorithm.ALLERGEN_CODES],
    )
