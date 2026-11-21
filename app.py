from flask import Flask, render_template, request, redirect

app = Flask(__name__)

#Home Page
@app.route("/")
def home():
    return render_template("home.html")

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







