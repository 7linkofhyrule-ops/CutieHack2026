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
    }


def menu_for(day, meal, profile):
    """Return (dishes, empty_title, empty_message) for one day + meal."""
    path = algorithm.menu_path_for(day)

    # The algorithm reads the quiz in its own key names (spice, not spicy)
    quiz = {
        "spice": profile["spicy"],
        "sweet": profile["sweet"],
        "savory": profile["savory"],
        "cuisines": profile["cuisines"],
    }

    try:
        dishes = algorithm.recommend(path, quiz, meal, limit=DISHES_SHOWN)
    except FileNotFoundError:
        return [], "Today's menu isn't available yet", (
            "We don't have a Glasgow or Lothian menu loaded for today. "
            "Check the official dining menus in the meantime."
        )

    if not dishes:
        return [], f"No {meal.lower()} menu today", (
            f"Glasgow and Lothian aren't listing any {meal.lower()} items for today. "
            "Try another meal above."
        )

    return dishes, "", ""


def homepage_response():
    profile = get_profile()

    # New visitors (or anyone who hasn't finished the quiz) see the welcome page + quiz button
    if profile is None:
        return render_template("welcome.html")

    today = today_la()

    meal = request.args.get("meal", "Lunch").title()
    if meal not in MEALS:
        meal = "Lunch"

    dishes, empty_title, empty_message = menu_for(today, meal, profile)

    return render_template(
        "dashboard.html",
        today_label=f"{today:%A, %B} {today.day}",
        meal=meal,
        meals=MEALS,
        profile=profile,
        dishes=dishes,
        empty_title=empty_title,
        empty_message=empty_message,
    )
