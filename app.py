import os
from datetime import timedelta

from flask import Flask, redirect, render_template, request, session, url_for

import init_db as db

app = Flask(__name__)

# Signs the cookie that identifies a returning user. Set a real SECRET_KEY outside of git.
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")
app.permanent_session_lifetime = timedelta(days=365)   # remember people for a year
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# Must match the checkbox values in quiz.html
CUISINES = {"mediterranean", "asian", "indian", "american", "hispanic", "african", "italian"}

db.init_user_db()


def current_user():
    """The user this browser belongs to, or None if we haven't seen them take the quiz."""
    return db.get_user_by_token(session.get("user_token"))

def get_or_create_user():
    """Return this visitor's user record, creating one if needed."""
    token = session.get("user_token")
    user = db.get_user_by_token(token) if token else None

    if user is None:
        user_id, token = db.create_user()
        session["user_token"] = token
        user = db.get_user_by_token(token)

    return user

# Home Page
@app.route("/")
def home():
    return render_template("welcome.html")

#Results Page
@app.route("/results", methods=["POST"])
def results():
    user = get_or_create_user()

    try:
        spice = int(request.form.get("spice", 5))
        sweet = int(request.form.get("sweet", 5))
        savory = int(request.form.get("savory", 5))
    except ValueError:
        return "Please choose valid taste ratings.", 400

    if not all(1 <= rating <= 10 for rating in (spice, sweet, savory)):
        return "Taste ratings must be between 1 and 10.", 400

    cuisines = request.form.getlist("cuisine")
    cuisines = [cuisine for cuisine in cuisines if cuisine in CUISINES]

    if len(cuisines) < 2:
        prefs = {
            "spice": spice,
            "sweet": sweet,
            "savory": savory,
            "cuisines": cuisines,
        }
        return render_template(
            "quiz.html",
            prefs=prefs,
            cuisines=CUISINES,
            error="Pick at least two cuisines to continue.",
        ), 400

    db.save_quiz_result(
        user["id"],
        spice,
        sweet,
        savory,
        cuisines,
    )

    return redirect(url_for("home"))


#Quiz Page
@app.route("/quiz")
def quiz():
    user = get_or_create_user()
    prefs = db.get_latest_result(user["id"])

    return render_template(
        "quiz.html",
        prefs=prefs,
        cuisines=CUISINES,
    )


if __name__ == "__main__":
    app.run(debug=True, port=5005)







