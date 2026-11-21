
import json
import secrets
import sqlite3

from datetime import date
from pathlib import Path
from flask import render_template, request, session

# Location of our database
BASE = Path(__file__).resolve().parent
DB_PATH = BASE / "instance" / "dining_finder.db"

MEALS = ("Breakfast", "Lunch", "Dinner")


# Connect to database
def connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row

    return db


# Create tables for users and food
def init_home_db():
    with connection() as db:

        db.execute("""
            CREATE TABLE IF NOT EXISTS profiles (
                visitor_id TEXT PRIMARY KEY,
                spicy INTEGER,
                sweet INTEGER,
                savory INTEGER,
                cuisines TEXT
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS menu_items (
                dining_hall TEXT,
                menu_date TEXT,
                meal TEXT,
                name TEXT,
                cuisine TEXT,
                spicy INTEGER DEFAULT 5,
                sweet INTEGER DEFAULT 5,
                savory INTEGER DEFAULT 5,
                PRIMARY KEY (
                    dining_hall,
                    menu_date,
                    meal,
                    name
                )
            )
        """)


# Give each visitor a unique ID
def visitor_id():
    if "visitor_id" not in session:
        session["visitor_id"] = secrets.token_urlsafe(24)

    session.permanent = True
    return session["visitor_id"]


# Retrieve saved quiz preferences
def get_profile():
    with connection() as db:
        row = db.execute(
            "SELECT * FROM profiles WHERE visitor_id = ?",
            (visitor_id(),)
        ).fetchone()

    if row is None:
        return None

    return {
        "spicy": row["spicy"],
        "sweet": row["sweet"],
        "savory": row["savory"],
        "cuisines": json.loads(row["cuisines"])
    }


# Save preferences when quiz is completed
def save_quiz_preferences(args):

    def rating(name):
        try:
            value = int(args.get(name, 5))
            return max(1, min(10, value))
        except (ValueError, TypeError):
            return 5

    profile = {
        "spicy": rating("spice"),
        "sweet": rating("sweet"),
        "savory": rating("savory"),
        "cuisines": args.getlist("cuisine")
    }

    # Do not save an empty quiz submission
    if not any(
        name in args
        for name in ("spice", "sweet", "savory", "cuisine")
    ):
        return get_profile()

    with connection() as db:
        db.execute("""
            INSERT INTO profiles
            (visitor_id, spicy, sweet, savory, cuisines)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(visitor_id)
            DO UPDATE SET
                spicy = excluded.spicy,
                sweet = excluded.sweet,
                savory = excluded.savory,
                cuisines = excluded.cuisines
        """, (
            visitor_id(),
            profile["spicy"],
            profile["sweet"],
            profile["savory"],
            json.dumps(profile["cuisines"])
        ))

    return profile


# Rank available meals based on taste
def ranked_menu(menu_date, meal, profile):

    with connection() as db:
        dishes = db.execute("""
            SELECT * FROM menu_items
            WHERE menu_date = ?
              AND meal = ?
              AND dining_hall IN ('Glasgow', 'Lothian')
        """, (menu_date, meal)).fetchall()

    ranked = []

    preferred = {
        cuisine.lower()
        for cuisine in profile["cuisines"]
    }

    for dish in dishes:

        score = 0

        for taste in ("spicy", "sweet", "savory"):
            score += 10 - abs(
                profile[taste] - dish[taste]
            )

        if dish["cuisine"].lower() in preferred:
            score += 12

        ranked.append({
            **dict(dish),
            "score": score
        })

    ranked.sort(
        key=lambda food: (-food["score"], food["name"])
    )

    return ranked[:8]


# Decide which homepage to display
def homepage_response():

    init_home_db()

    profile = get_profile()

    today = date.today().isoformat()

    # First-time user
    if profile is None:
        return render_template(
            "welcome.html",
            today=today
        )

    # Returning user
    meal = request.args.get("meal", "Lunch").title()

    if meal not in MEALS:
        meal = "Lunch"

    dishes = ranked_menu(today, meal, profile)

    return render_template(
        "dashboard.html",
        today=today,
        meal=meal,
        meals=MEALS,
        profile=profile,
        dishes=dishes
    )
