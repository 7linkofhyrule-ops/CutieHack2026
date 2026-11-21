from flask import Flask, render_template, request, redirect
from datetime import timedelta
from pathlib import Path
import os
import secrets

from home_feature import (
    homepage_response,
    save_quiz_preferences,
    init_home_db
)

app = Flask(__name__)
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=180)

keyfile = Path(app.instance_path) / "session_secret.txt"
keyfile.parent.mkdir(parents=True, exist_ok=True)

if not keyfile.exists():
    keyfile.write_text(secrets.token_hex(32))

app.secret_key = (
    os.environ.get("FLASK_SECRET_KEY")
    or keyfile.read_text().strip()
)

init_home_db()

#Home Page
@app.route("/")
def home():
    return render_template("welcome.html")

#Results Page
@app.route("/results")
def results():
    spicy = request.args.get("spice", default=5, type = int)
    sweet = request.args.get("sweet", default=5, type = int)
    savory = request.args.get("savory", default=5,type = int)

    cuisines = request.args.getlist("cuisine")

    print("Spicy:", spicy)
    print("Sweet:", sweet)
    print("Savory:", savory)
    print("Cuisines:", cuisines)

    if len(cuisines) < 2:
        return redirect("/quiz")

    save_quiz_preferences(request.args)

    return render_template(
        "results.html",
        spicy=spicy,
        sweet=sweet,
        savory=savory,
        cuisines=cuisines
        
    )

#Quiz Page
@app.route("/quiz")
def quiz():
    return render_template("quiz.html")


if __name__ == "__main__":
    app.run(debug=True)







