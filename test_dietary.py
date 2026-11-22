"""Tests for the dietary/allergen feature.   Run:  python -m unittest test_dietary -v

Uses a throwaway database and the INVENTED demo menu, so it never touches users.db
or your real menus.
"""
import os
import random
import re
import sqlite3
import tempfile
import unittest
from html import unescape as html_unescape
from datetime import date
from pathlib import Path

import init_db

# Point the user database at a temp file BEFORE app.py is imported (it initializes on import).
_TMP = tempfile.mkdtemp()
init_db.DB_PATH = os.path.join(_TMP, "users.db")

import algorithm as alg          # noqa: E402
import app as app_module         # noqa: E402
import home_feature              # noqa: E402

HERE = Path(__file__).resolve().parent
DEMO = HERE / "demo_menus" / "DEMO-dietary-MENU.txt"
REAL_1121 = HERE / "txt4algo" / "11-21-2026-MENU.txt"
REAL_1122 = HERE / "txt4algo" / "11-22-2026-MENU.txt"


def dish(flags, **kw):
    base = {"name": "X", "spice": 5, "sweet": 5, "savory": 5, "cuisine": "asian",
            "meal": "Lunch", "location": "G", "flags": flags}
    base.update(kw)
    return base


def fz(*codes):
    return frozenset(codes)


class LegendTests(unittest.TestCase):
    def test_exact_legend_labels_in_legend_order(self):
        self.assertEqual([i["label"] for i in alg.LEGEND], [
            "Vegan", "Vegetarian", "Gluten Free", "Contains Milk", "Contains Eggs",
            "Contains Fish", "Contains Crustacean Shellfish", "Contains Tree Nuts",
            "Contains Peanuts", "Contains Wheat", "Contains Soybeans", "Contains Sesame"])

    def test_codes_are_safe_for_the_file_and_profile_formats(self):
        for code in alg.LEGEND_CODES:
            self.assertFalse(set(code) & set("-:+ "), code)

    def test_flags_from_labels(self):
        self.assertEqual(alg.flags_from_labels(["Vegan", " contains   milk "]), fz("vegan", "milk"))
        with self.assertRaises(ValueError):
            alg.flags_from_labels(["Halal"])


class ParserTests(unittest.TestCase):
    def test_existing_menu_files_still_parse_as_before_with_unknown_dietary_info(self):
        a, b = alg.load_menu(REAL_1121), alg.load_menu(REAL_1122)
        self.assertEqual((len(a), len(b)), (75, 152))     # 76th record is the known-bad Tuna Salad row
        self.assertTrue(all(i["flags"] is None for i in a + b))

    def test_round_trip(self):
        rng = random.Random(1)
        for _ in range(200):
            flags = frozenset(rng.sample(alg.LEGEND_CODES, rng.randint(0, 5)))
            rec = alg.format_menu_record("Pad-Thai Bowl", 3, 4, 5, "Asian", "Lunch", "L", flags)
            self.tmp = Path(_TMP) / "rt.txt"
            self.tmp.write_text(rec + "\n", encoding="utf8")
            (item,) = alg.load_menu(self.tmp)
            self.assertEqual((item["name"], item["flags"], item["cuisine"]),
                             ("Pad-Thai Bowl", flags, "asian"))

    def test_none_and_unknown_are_different(self):
        self.assertEqual(alg.parse_flags("none"), frozenset())
        self.assertIsNone(alg.parse_flags("unknown"))
        self.assertEqual(alg.format_flags(None), "unknown")
        self.assertEqual(alg.format_flags(frozenset()), "none")

    def test_bad_records_are_skipped_not_trusted(self):
        f = Path(_TMP) / "bad.txt"
        f.write_text("Good-1-1-1-asian-Lunch-G-vegan-:"
                     "Hyphen code-1-1-1-asian-Lunch-G-gluten-free-:"      # code must be gluten_free
                     "Made up code-1-1-1-asian-Lunch-G-halal-:"
                     "Missing field-1-1-7-Dinner-G-:"
                     "Bad meal-1-1-1-asian-Brunch-G-vegan-:", encoding="utf8")
        self.assertEqual([i["name"] for i in alg.load_menu(f)], ["Good"])

    def test_writer_rejects_bad_input(self):
        for bad in (dict(name="A:B"), dict(flags=fz("halal")), dict(meal="Brunch")):
            args = dict(name="A", spice=1, sweet=1, savory=1, cuisine="asian", meal="Lunch",
                        location="G", flags=fz())
            args.update(bad)
            with self.assertRaises(ValueError):
                alg.format_menu_record(**args)


class FilterRuleTests(unittest.TestCase):
    def eligible(self, flags, *restrictions):
        return alg.check_restrictions(dish(flags), frozenset(restrictions)) is None

    def test_each_allergen_is_excluded_only_when_avoided(self):
        for code in alg.ALLERGEN_CODES:
            other = next(c for c in alg.ALLERGEN_CODES if c != code)
            self.assertFalse(self.eligible(fz(code), code), code)
            self.assertFalse(self.eligible(fz(code, other), code), code)
            self.assertTrue(self.eligible(fz(other), code), code)
            self.assertTrue(self.eligible(fz(), code), code)           # 'none' = nothing listed
            self.assertTrue(self.eligible(fz(code)), code)             # not avoided -> fine

    def test_unknown_dietary_info_is_hidden_whenever_any_restriction_exists(self):
        for code in alg.LEGEND_CODES:
            self.assertEqual(alg.check_restrictions(dish(None), frozenset([code]))[0], "unknown")
        self.assertIsNone(alg.check_restrictions(dish(None), frozenset()))   # no restrictions: shown

    def test_vegan(self):
        self.assertTrue(self.eligible(fz("vegan"), "vegan"))
        self.assertFalse(self.eligible(fz(), "vegan"))
        self.assertFalse(self.eligible(fz("vegetarian"), "vegan"))
        for animal in ("milk", "eggs", "fish", "shellfish"):
            self.assertFalse(self.eligible(fz("vegan", animal), "vegan"), animal)

    def test_vegetarian(self):
        self.assertTrue(self.eligible(fz("vegetarian"), "vegetarian"))
        self.assertTrue(self.eligible(fz("vegan"), "vegetarian"))            # vegan is stricter
        self.assertFalse(self.eligible(fz(), "vegetarian"))
        self.assertTrue(self.eligible(fz("vegetarian", "milk"), "vegetarian"))
        self.assertFalse(self.eligible(fz("vegetarian", "fish"), "vegetarian"))
        self.assertFalse(self.eligible(fz("vegetarian", "shellfish"), "vegetarian"))

    def test_gluten_free(self):
        self.assertTrue(self.eligible(fz("gluten_free"), "gluten_free"))
        self.assertFalse(self.eligible(fz(), "gluten_free"))
        self.assertFalse(self.eligible(fz("gluten_free", "wheat"), "gluten_free"))

    def test_combined_restrictions_all_apply(self):
        r = ("vegan", "gluten_free", "peanuts")
        self.assertTrue(self.eligible(fz("vegan", "gluten_free"), *r))
        self.assertFalse(self.eligible(fz("vegan"), *r))
        self.assertFalse(self.eligible(fz("vegan", "gluten_free", "peanuts"), *r))

    def test_unknown_restriction_code_is_rejected_not_ignored(self):
        with self.assertRaises(ValueError):
            alg.filter_menu([dish(fz())], ["peanut"])          # typo must not silently disable it


class RankingTests(unittest.TestCase):
    QUIZ = {"spice": 5, "sweet": 5, "savory": 5, "cuisines": ["asian", "american"]}

    def test_profile_string_format_is_backward_compatible(self):
        self.assertEqual(alg.build_profile(7, 5, 6, "asian", "Lunch"), "7-5-6-asian-Lunch-")
        self.assertEqual(alg.build_profile(7, 5, 6, "asian", "Lunch", ["peanuts", "vegan"]),
                         "7-5-6-asian-Lunch-vegan+peanuts-")
        self.assertEqual(alg.score_item("0-2-7-italian-Lunch-", dish(None, spice=0, sweet=2,
                         savory=7, cuisine="italian")), 14)       # old 5-field string still works

    def test_restrictions_do_not_change_taste_order_of_survivors(self):
        base = alg.recommend_detailed(DEMO, {**self.QUIZ}, "Lunch")["dishes"]
        safe = alg.recommend_detailed(DEMO, {**self.QUIZ, "restrictions": ["peanuts"]}, "Lunch")["dishes"]
        self.assertEqual([d["name"] for d in safe],
                         [d["name"] for d in base if d["flags"] is not None
                          and "peanuts" not in d["flags"]])

    def test_rank_menu_called_directly_still_filters(self):
        items = [dish(fz("peanuts"), name="P"), dish(fz(), name="OK")]
        ranked = alg.rank_menu(items, [alg.build_profile(5, 5, 5, "asian", "Lunch", ["peanuts"])])
        self.assertEqual([d["name"] for d in ranked], ["OK"])

    def test_hidden_report_adds_up(self):
        r = alg.recommend_detailed(DEMO, {**self.QUIZ, "restrictions": ["peanuts"]}, "Dinner")
        self.assertEqual((r["total"], r["hidden"], r["dishes"]),
                         (3, {"allergen": 2, "diet": 0, "unknown": 1}, []))

    def test_safety_property_on_random_users_and_menus(self):
        """No matter the quiz answers or restrictions, no forbidden dish is ever returned."""
        rng = random.Random(7)
        menus = [alg.load_menu(DEMO)] + [alg.load_menu(REAL_1122)]
        for _ in range(3000):
            items = list(rng.choice(menus))
            for it in items:          # randomize flags, including unknown
                it["flags"] = None if rng.random() < .25 else frozenset(
                    rng.sample(alg.LEGEND_CODES, rng.randint(0, 4)))
            restr = frozenset(rng.sample(alg.LEGEND_CODES, rng.randint(0, 4)))
            profile = alg.build_profile(rng.randint(1, 10), rng.randint(1, 10), rng.randint(1, 10),
                                        rng.choice(["asian", "italian", "indian"]), "Lunch", restr)
            out = alg.rank_menu(items, [profile])
            for d in out:
                if restr:
                    self.assertIsNotNone(d["flags"], "unknown dish recommended to a restricted user")
                    self.assertFalse(d["flags"] & restr & alg.ALLERGEN_CODES)
                    for need in restr & alg.DIET_CODES:
                        self.assertTrue(need in d["flags"] or (need == "vegetarian" and "vegan" in d["flags"]))
            eligible, excluded = alg.filter_menu(items, restr)
            self.assertEqual(len(eligible) + len(excluded), len(items))
            self.assertEqual(len(out), len(eligible))


class MigrationTests(unittest.TestCase):
    def test_old_database_is_upgraded_in_place(self):
        path = os.path.join(_TMP, "old.db")
        conn = sqlite3.connect(path)
        conn.executescript("""
            CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, token TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, last_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE quiz_results (id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                spice INTEGER NOT NULL, sweet INTEGER NOT NULL, savory INTEGER NOT NULL,
                cuisines TEXT NOT NULL, taken_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            INSERT INTO users (token) VALUES ('tok');
            INSERT INTO quiz_results (user_id, spice, sweet, savory, cuisines) VALUES (1, 7, 3, 6, 'asian,indian');
        """)
        conn.commit()
        conn.close()
        saved, init_db.DB_PATH = init_db.DB_PATH, path
        try:
            init_db.init_user_db()
            init_db.init_user_db()                                   # idempotent
            self.assertEqual(init_db.get_latest_result(1),
                             {**init_db.get_latest_result(1), "spice": 7, "cuisines": ["asian", "indian"],
                              "restrictions": None})
            self.assertEqual(init_db.get_user_by_token("tok")["id"], 1)
        finally:
            init_db.DB_PATH = saved


# ------------------------------------------------------------------ Flask flow

def checked_boxes(html):
    return set(re.findall(r'name="restriction" value="(\w+)" checked', html))


def shown_dishes(html):
    return re.findall(r'class="food-information">.*?<h3>([^<]+)</h3>', html, re.S)


class FlaskFlowTests(unittest.TestCase):
    FORM = {"spice": 5, "sweet": 5, "savory": 5, "cuisine": ["asian", "american"]}

    def setUp(self):
        app_module.app.testing = True
        self.client = app_module.app.test_client()
        os.environ["DINING_MENU_FILE"] = str(DEMO)
        home_feature.today_la = lambda: date(2026, 11, 21)
        # fresh database each test
        for t in ("quiz_results", "users"):
            with init_db.connect() as c:
                c.execute(f"DELETE FROM {t}")

    def tearDown(self):
        os.environ.pop("DINING_MENU_FILE", None)

    def rows(self):
        with init_db.connect() as c:
            return [tuple(r) for r in c.execute("SELECT restrictions FROM quiz_results ORDER BY id")]

    def take(self, restrictions, **extra):
        return self.client.post("/results", data={**self.FORM, "restriction": restrictions, **extra})

    def meal(self, meal):
        return self.client.get(f"/?meal={meal}").get_data(as_text=True)

    def test_new_visitor_sees_welcome_and_quiz_has_all_12_exact_labels_unchecked(self):
        self.assertIn("Take your flavor quiz", self.client.get("/").get_data(as_text=True))
        html = self.client.get("/quiz").get_data(as_text=True)
        for item in alg.LEGEND:
            self.assertIn(f'value="{item["code"]}"', html)
            self.assertIn(f"<span>{item['label']}</span>", html)
        self.assertEqual(checked_boxes(html), set())
        self.assertIn("Must avoid", html)
        self.assertIn("Preferences", html)

    def test_restrictions_are_saved_in_legend_order_and_prefill_on_retake(self):
        self.client.get("/quiz")
        r = self.take(["peanuts", "vegetarian", "gluten_free"])
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.rows(), [("vegetarian,gluten_free,peanuts",)])
        self.assertEqual(checked_boxes(self.client.get("/quiz").get_data(as_text=True)),
                         {"vegetarian", "gluten_free", "peanuts"})

    def test_retake_with_nothing_ticked_clears_restrictions_and_keeps_history(self):
        self.client.get("/quiz")
        self.take(["peanuts"])
        self.take([])
        self.assertEqual(self.rows(), [("peanuts",), ("",)])           # history kept, latest = none
        self.assertEqual(checked_boxes(self.client.get("/quiz").get_data(as_text=True)), set())

    def test_unrecognized_dietary_value_is_rejected_and_nothing_is_saved(self):
        self.client.get("/quiz")
        r = self.take(["peanuts", "peanut-typo"])
        self.assertEqual(r.status_code, 400)
        html = html_unescape(r.get_data(as_text=True))
        self.assertIn("wasn't recognized", html)
        self.assertEqual(checked_boxes(html), {"peanuts"})            # valid ticks preserved
        self.assertEqual(self.rows(), [])

    def test_too_few_cuisines_keeps_the_ticked_restrictions(self):
        self.client.get("/quiz")
        r = self.client.post("/results", data={**self.FORM, "cuisine": ["asian"],
                                               "restriction": ["milk", "vegan"]})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(checked_boxes(r.get_data(as_text=True)), {"milk", "vegan"})
        self.assertEqual(self.rows(), [])

    def test_filtering_on_the_dashboard(self):
        self.client.get("/quiz")
        self.take(["peanuts"])
        lunch = shown_dishes(self.meal("Lunch"))
        for banned in ("DEMO Peanut Noodles", "DEMO Pasta Mystery", "DEMO Mac-n-Cheese"):
            self.assertNotIn(banned, lunch)                              # allergen + unknown data
        self.assertIn("DEMO Chicken Rice Bowl", lunch)
        self.assertIn("hidden for your safety", self.meal("Lunch"))

        self.take(["vegan", "gluten_free"])
        self.assertEqual(shown_dishes(self.meal("Lunch")), ["DEMO Garden Salad Plain"])
        self.assertEqual(shown_dishes(self.meal("Breakfast")), ["DEMO Oat Bowl"])

        self.take(["tree_nuts", "shellfish", "wheat"])                  # several allergens at once
        lunch = shown_dishes(self.meal("Lunch"))
        for banned in ("DEMO Tree Nut Granola", "DEMO Shrimp Tacos", "DEMO Veggie Wrap",
                       "DEMO Peanut Noodles", "DEMO Contradictory Vegan Pizza"):
            self.assertNotIn(banned, lunch)
        self.assertEqual(sorted(lunch), ["DEMO Chicken Rice Bowl", "DEMO Garden Salad Plain"])

    def test_dish_cards_show_labels_and_never_claim_safe(self):
        self.client.get("/quiz")
        self.take([])
        html = self.meal("Lunch")
        self.assertIn("Contains Peanuts", html)
        self.assertIn("Dietary info unavailable", html)                 # unknown dishes shown, labeled
        self.assertNotRegex(html, r"(?i)\bsafe to eat\b|allergen[- ]free|100% safe")
        self.assertIn("Contains Crustacean Shellfish", self.meal("Lunch"))

    def test_empty_states(self):
        self.client.get("/quiz")
        self.take(["peanuts"])
        html = self.meal("Dinner")                                       # all 3 dinner dishes blocked
        self.assertEqual(shown_dishes(html), [])
        self.assertIn("Nothing matches your dietary needs for dinner", html)
        self.assertIn("2 contain an allergen you avoid", html)
        self.assertIn("1 has no dietary info", html)

        os.environ["DINING_MENU_FILE"] = str(Path(_TMP) / "does-not-exist.txt")
        self.assertIn("menu isn't available yet", html_unescape(self.meal("Lunch")))

        os.environ["DINING_MENU_FILE"] = str(REAL_1121)                  # real menu: no Breakfast rows
        self.assertIn("No breakfast menu today", self.meal("Breakfast"))

    def test_real_menus_have_no_dietary_data_so_restricted_users_get_a_clear_empty_state(self):
        os.environ["DINING_MENU_FILE"] = str(REAL_1121)
        self.client.get("/quiz")
        self.take(["milk"])
        html = self.meal("Lunch")
        self.assertEqual(shown_dishes(html), [])
        self.assertIn("have no dietary info, so we can't confirm them", html_unescape(html))
        self.take([])                                                   # no restrictions: works as before
        self.assertEqual(len(shown_dishes(self.meal("Lunch"))), 8)

    def test_existing_user_without_dietary_answers_is_nudged_and_unfiltered(self):
        self.client.get("/quiz")                                        # creates the user + cookie
        with init_db.connect() as c:
            user_id = c.execute("SELECT id FROM users").fetchone()["id"]
        init_db.save_quiz_result(user_id, 5, 5, 5, ["asian", "american"])    # old-style save -> NULL
        html = self.meal("Lunch")
        self.assertIn("You haven't set dietary needs", html_unescape(html))
        self.assertNotIn("Filtered by your must-avoid list", html)
        self.assertIn("DEMO Peanut Noodles", html)                       # unfiltered, as before

    def test_profile_card_lists_saved_restrictions(self):
        self.client.get("/quiz")
        self.take(["vegetarian", "milk"])
        html = self.meal("Lunch")
        self.assertIn("Must be: Vegetarian", html)
        self.assertIn("Contains Milk", html)

    def test_results_template_renders_with_and_without_dietary_fields(self):
        with app_module.app.test_request_context("/"):
            from flask import render_template
            matches = alg.recommend(DEMO, {**{"spice": 5, "sweet": 5, "savory": 5,
                                              "cuisines": ["asian", "american"]}}, "Lunch", limit=3)
            html = render_template("results.html", spicy=5, sweet=5, savory=5, cuisines=["asian"],
                                   restriction_labels=["Vegan"], matches=matches + [{"name": "Plain"}])
            self.assertIn("Must avoid", html)
            self.assertIn("Dietary info unavailable", html)           # dish with no dietary fields


if __name__ == "__main__":
    unittest.main()
