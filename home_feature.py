import sqlite3
from datetime import date
from pathlib import Path

from flask import render_template, request, session, redirect, url_for

import init_db as db


BASE = Path(__file__).resolve().parent
DB_PATH = BASE / "instance" / "dining_finder.db"

MEALS = ("Breakfast", "Lunch", "Dinner")
MAX_SCORE = 42  # 3 tastes x 10 points + 12 cuisine bonus


def connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_home_db():
    """Menu table only. Quiz answers live in users.db (init_db.py)."""
    with connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS menu_items (
                dining_hall TEXT,
                menu_date TEXT,
                meal TEXT,
                name TEXT,
                cuisine TEXT,
                spicy INTEGER DEFAULT 5,
                sweet INTEGER DEFAULT 5,
                savory INTEGER DEFAULT 5,
                PRIMARY KEY (dining_hall, menu_date, meal, name)
            )
        """)


def get_profile():
    """Latest quiz answers for this browser, shaped for the dashboard. None if no quiz yet."""
    user = db.get_user_by_token(session.get("user_token"))
    if user is None:
        return None

    result = db.get_latest_result(user["id"])
    if result is None:
        return None

    return {
        "spicy": result["spice"],
        "sweet": result["sweet"],
        "savory": result["savory"],
        "cuisines": result["cuisines"],
    }


def ranked_menu(menu_date, meal, profile):
    with connection() as conn:
        dishes = conn.execute("""
            SELECT * FROM menu_items
            WHERE menu_date = ?
              AND meal = ?
              AND dining_hall IN ('Glasgow', 'Lothian')
        """, (menu_date, meal)).fetchall()

    preferred = {c.lower() for c in profile["cuisines"]}
    ranked = []

    for dish in dishes:
        score = 0
        for taste in ("spicy", "sweet", "savory"):
            score += 10 - abs(profile[taste] - (dish[taste] or 5))

        if (dish["cuisine"] or "").lower() in preferred:
            score += 12

        ranked.append({
            **dict(dish),
            "score": score,
            "match": round(score / MAX_SCORE * 100),
        })

    ranked.sort(key=lambda food: (-food["score"], food["name"]))
    return ranked[:8]


def homepage_response():
    profile = get_profile()
    today = date.today()

    if profile is None:
        return redirect(url_for("quiz"))

    meal = request.args.get("meal", "Lunch").title()
    if meal not in MEALS:
        meal = "Lunch"

    return render_template(
        "dashboard.html",
        today_label=f"{today:%A, %B} {today.day}",
        meal=meal,
        meals=MEALS,
        profile=profile,
        dishes=ranked_menu(today.isoformat(), meal, profile),
    )