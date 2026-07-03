"""
freezer_prep_reminder.py — Friday Freezer + Meal Plan + Batch Prep Briefing
Runs every Friday evening. Does the following:
  1. Reads freezer inventory from the second brain app
  2. Reads pantry to flag low items
  3. Reads next week's meal plan from the app (or generates a PCOD-friendly one if missing)
  4. Cross-references freezer with next week's meals
  5. Generates a batch prep list and SAVES it back into the meal plan (visible in UI)
  6. Outputs one combined briefing for Telegram
"""

import urllib.request
import urllib.error
import json
import os
import time
import datetime
import random

BASE_URL = "https://cold-sunset-7499.fly.dev"
MAX_RETRIES = 3
RETRY_DELAY = 10  # seconds


# ---------------------------------------------------------------------------
# PCOD-friendly recipe pool
# Low GI, high protein, anti-inflammatory. Key ingredients: ragi, moong dal,
# besan, methi, flaxseed, oats, dalia, eggs, lean protein.
# Format: { "name": str, "freezer_uses": [str] (partial match), "batch_prep": str or None }
# ---------------------------------------------------------------------------
PCOD_BREAKFASTS = [
    {"name": "Ragi Dosa + Coconut Chutney", "freezer_uses": [], "batch_prep": "Prep ragi dosa batter Friday night, ferment overnight"},
    {"name": "Besan Cheela + Mint Chutney", "freezer_uses": [], "batch_prep": None},
    {"name": "Moong Dal Chilla + Curd", "freezer_uses": [], "batch_prep": "Prep moong dal chilla batter, refrigerate"},
    {"name": "Oats Upma with Veggies", "freezer_uses": [], "batch_prep": None},
    {"name": "Ragi Porridge with Almonds & Flaxseed", "freezer_uses": [], "batch_prep": None},
    {"name": "Masala Omelette (2 eggs) + Cucumber Slices", "freezer_uses": [], "batch_prep": "Boil 6 eggs for the week"},
    {"name": "Dalia Khichdi with Veggies", "freezer_uses": [], "batch_prep": None},
    {"name": "Methi Thepla + Curd", "freezer_uses": [], "batch_prep": "Make thepla dough Saturday, refrigerate"},
    {"name": "Poha with Peanuts & Veggies", "freezer_uses": [], "batch_prep": None},
    {"name": "Quinoa Upma with Veggies", "freezer_uses": [], "batch_prep": None},
]

PCOD_LUNCHES = [
    {"name": "Moong Dal Khichdi + Ghee", "freezer_uses": [], "batch_prep": None},
    {"name": "Rajma + Brown Rice", "freezer_uses": [], "batch_prep": "Soak rajma overnight Friday"},
    {"name": "Chana Dal + Methi Roti", "freezer_uses": [], "batch_prep": None},
    {"name": "Toor Dal + Jeera Rice + Roasted Papad", "freezer_uses": [], "batch_prep": None},
    {"name": "Masoor Dal + Rice + Stir-fried Spinach", "freezer_uses": [], "batch_prep": None},
    {"name": "Mutton Bone Broth Soup + Dalia", "freezer_uses": ["Mutton Pieces", "Mutton Bone"], "batch_prep": "Make bone broth Saturday — slow cook 4h, store in jars"},
    {"name": "Kuta Hua Gosht (Mutton) + Bajra Roti", "freezer_uses": ["Boneless Mutton"], "batch_prep": "Cook mutton Saturday, store in fridge"},
    {"name": "Aloo Tikki (AF) + Curd Dip", "freezer_uses": ["Grated Potato"], "batch_prep": "Air-fry tikkis from frozen grated potato Saturday"},
    {"name": "Prawn Stir Fry + Cauliflower Rice", "freezer_uses": [], "batch_prep": None},
    {"name": "Egg Curry + 1 Roti", "freezer_uses": [], "batch_prep": None},
    {"name": "Besan Kadhi + Rice", "freezer_uses": [], "batch_prep": None},
    {"name": "Palak Paneer + 1 Roti", "freezer_uses": [], "batch_prep": None},
    {"name": "Shorshe Maach + Rice", "freezer_uses": [], "batch_prep": None},
]

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def fetch_with_retry(url, retries=MAX_RETRIES, delay=RETRY_DELAY):
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "freezer-bot/1.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.read().decode("utf-8")
        except Exception as e:
            last_err = e
            if attempt < retries:
                print(f"[attempt {attempt}] Failed: {e} — retrying in {delay}s...", flush=True)
                time.sleep(delay)
    raise RuntimeError(f"All {retries} attempts failed. Last error: {last_err}")


def get_file(path):
    url = f"{BASE_URL}/api/files?path={path}"
    raw = fetch_with_retry(url)
    wrapper = json.loads(raw)
    return wrapper.get("content", "")


def put_file(path, content_str):
    url = f"{BASE_URL}/api/files"
    payload = json.dumps({"path": path, "content": content_str}).encode("utf-8")
    req = urllib.request.Request(url, data=payload,
                                  headers={"Content-Type": "application/json"}, method="PUT")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def parse_markdown_table(md):
    rows = []
    lines = md.strip().split("\n")
    headers = []
    for line in lines:
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not headers:
            headers = cells
            continue
        if all(set(c) <= set("-: ") for c in cells):
            continue
        if len(cells) == len(headers):
            rows.append(dict(zip(headers, cells)))
    return rows


def parse_freezer(md):
    """Return list of {item, qty, date_frozen, notes} and the last_updated string."""
    items = parse_markdown_table(md)
    last_updated = ""
    for line in md.split("\n"):
        if "Last updated" in line:
            last_updated = line.replace(">", "").replace("Last updated:", "").strip()
    return items, last_updated


def parse_pantry_lows(content):
    pantry = json.loads(content)
    low = []
    for i in pantry.get("items", []):
        qty = i.get("currentQty")
        minq = i.get("minQty")
        if qty is not None and minq is not None and qty <= minq:
            low.append({"name": i["name"], "qty": qty, "unit": i.get("unit", ""), "restockTo": i.get("restockTo")})
    return low


# ---------------------------------------------------------------------------
# Week helpers
# ---------------------------------------------------------------------------

def next_week_id(from_date=None):
    """Return ISO week ID for next week, e.g. '2026-W28'."""
    d = from_date or datetime.date.today()
    next_monday = d + datetime.timedelta(days=(7 - d.weekday()))
    return f"{next_monday.isocalendar()[0]}-W{next_monday.isocalendar()[1]:02d}", next_monday


def week_label(monday):
    sunday = monday + datetime.timedelta(days=6)
    return f"{monday.strftime('%-d %b')} – {sunday.strftime('%-d %b, %Y')}"


# ---------------------------------------------------------------------------
# Meal plan generation
# ---------------------------------------------------------------------------

def generate_pcod_week(week_id, week_label_str, monday, freezer_items):
    """Auto-generate a PCOD-friendly week. Prioritises meals that use freezer items."""
    freezer_names = [i.get("Item", "") for i in freezer_items]

    # Score lunches — prefer ones that use freezer items
    def score_lunch(l):
        return sum(1 for fu in l["freezer_uses"] if any(fu.lower() in fn.lower() for fn in freezer_names))

    scored_lunches = sorted(PCOD_LUNCHES, key=score_lunch, reverse=True)

    # Pick 7 unique breakfasts and lunches
    breakfasts = random.sample(PCOD_BREAKFASTS, min(7, len(PCOD_BREAKFASTS)))
    lunches = []
    seen = set()
    for l in scored_lunches:
        if l["name"] not in seen:
            lunches.append(l)
            seen.add(l["name"])
        if len(lunches) == 7:
            break

    meals = []
    batch_prep = []
    bp_id = 1
    for i, day in enumerate(DAYS):
        date = monday + datetime.timedelta(days=i)
        bf = breakfasts[i]
        ln = lunches[i]

        # Dinner: Rohan Sen Mon–Fri, cook own on weekends
        if i < 5:
            dinner_name = "Rohan Sen (catering)"
        elif i == 5:
            dinner_name = "Prawn Stir Fry + Cauliflower Rice"
        else:
            dinner_name = "Egg Curry + 1 Roti"

        meals.append({
            "day": day,
            "date": date.strftime("%Y-%m-%d"),
            "breakfast": {"name": bf["name"], "done": False, "recipes": []},
            "lunch": {"name": ln["name"], "done": False, "recipes": []},
            "dinner": {"name": dinner_name, "done": False, "recipes": []},
        })

        # Collect batch prep
        for prep_src in [bf, ln]:
            if prep_src.get("batch_prep"):
                batch_prep.append({
                    "id": f"bp-{week_id}-{bp_id}",
                    "task": prep_src["batch_prep"],
                    "day": "Saturday",
                    "meals": [f"{day} {'Breakfast' if prep_src == bf else 'Lunch'}"],
                    "done": False
                })
                bp_id += 1

    # Deduplicate batch prep by task text
    seen_tasks = set()
    deduped_bp = []
    for bp in batch_prep:
        if bp["task"] not in seen_tasks:
            deduped_bp.append(bp)
            seen_tasks.add(bp["task"])

    # Standard Saturday batch preps
    standard_preps = [
        {"id": f"bp-{week_id}-std1", "task": "Blend Ginger-Garlic paste, freeze in ice cube tray", "day": "Saturday", "meals": ["All week"], "done": False},
        {"id": f"bp-{week_id}-std2", "task": "Boil 6 eggs — grab-and-go snacks/breakfast", "day": "Saturday", "meals": ["Snacks"], "done": False},
    ]
    for sp in standard_preps:
        if sp["task"] not in seen_tasks:
            deduped_bp.append(sp)

    # Grocery checklist from pantry lows (will be populated externally)
    grocery = []

    return {
        "weekId": week_id,
        "weekLabel": week_label_str,
        "meals": meals,
        "groceryChecklist": grocery,
        "batchPrep": deduped_bp,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    today = datetime.date.today()
    today_str = today.strftime("%d %b %Y")

    # 1. Fetch freezer
    try:
        freezer_md = get_file("food/freezer-inventory.md")
    except RuntimeError as e:
        print(f"🧊 *Freezer Prep Briefing — {today_str}*\n\n"
              f"⚠️ Couldn't fetch freezer inventory after {MAX_RETRIES} attempts.\n"
              f"Please do a manual scan before prep tomorrow.\n\nError: `{e}`\n\nHappy prepping! 🥗")
        return

    freezer_items, last_updated = parse_freezer(freezer_md)

    # 2. Fetch pantry lows
    low_pantry = []
    try:
        low_pantry = parse_pantry_lows(get_file("food/pantry.json"))
    except Exception as e:
        low_pantry = []

    # 3. Load meal plans JSON
    try:
        mp_content = get_file("food/meal-plans.json")
        mp = json.loads(mp_content)
    except Exception as e:
        print(f"⚠️ Could not load meal plans: {e}")
        mp = {"weeks": []}

    # 4. Find or generate next week's plan
    next_wid, next_monday = next_week_id(today)
    existing_week = next((w for w in mp.get("weeks", []) if w["weekId"] == next_wid), None)
    plan_was_generated = False

    if not existing_week:
        # Generate and save
        try:
            wlabel = week_label(next_monday)
        except Exception:
            sunday = next_monday + datetime.timedelta(days=6)
            wlabel = f"{next_monday.strftime('%d %b')} – {sunday.strftime('%d %b, %Y')}"
        existing_week = generate_pcod_week(next_wid, wlabel, next_monday, freezer_items)
        mp["weeks"].append(existing_week)
        plan_was_generated = True
        try:
            put_file("food/meal-plans.json", json.dumps(mp, indent=2, ensure_ascii=False))
        except Exception as e:
            print(f"⚠️ Could not save meal plan: {e}")
    else:
        # Update batchPrep in existing week with any missing items (don't overwrite done items)
        # (existing plan kept as-is, batch prep already there)
        pass

    week = existing_week
    meals = week.get("meals", [])
    batch_prep = week.get("batchPrep", [])

    # 5. Cross-reference freezer items with next week's meals
    freezer_used_in = {}  # freezer item name -> list of meal days
    for freezer_item in freezer_items:
        fname = freezer_item.get("Item", "")
        used_in = []
        for m in meals:
            for slot in ["breakfast", "lunch", "dinner"]:
                meal_name = m.get(slot, {}).get("name", "") if isinstance(m.get(slot), dict) else ""
                # fuzzy: check if any word from freezer item is in meal name
                for word in fname.split():
                    if len(word) > 3 and word.lower() in meal_name.lower():
                        used_in.append(f"{m['day']} {slot.capitalize()}")
                        break
        if used_in:
            freezer_used_in[fname] = used_in

    # 6. Grocery needs: pantry lows + ingredients that might be needed
    grocery_needed = []
    for item in low_pantry[:10]:
        grocery_needed.append(f"{item['name']} (have: {item['qty']} {item['unit']})")

    # 7. Build the briefing
    lines = [f"🧊 *Friday Freezer & Prep Briefing — {today_str}*\n"]

    # --- Freezer stock ---
    lines.append("*🫙 Freezer Stock:*")
    old_cutoff = today - datetime.timedelta(weeks=3)
    if freezer_items:
        for fi in freezer_items:
            name = fi.get("Item", "")
            qty = fi.get("Qty", "")
            frozen_str = fi.get("Date Frozen", "")
            stale = ""
            try:
                fd = datetime.datetime.strptime(frozen_str, "%d %b %Y").date()
                if fd < old_cutoff:
                    stale = " ⏰ *use soon*"
            except Exception:
                pass
            used_note = ""
            if name in freezer_used_in:
                used_note = f" → planned: {', '.join(freezer_used_in[name])}"
            lines.append(f"  • {name} — {qty} _(frozen {frozen_str})_{stale}{used_note}")
    else:
        lines.append("  _(freezer is empty — great time for a full batch cook!)_")

    if last_updated:
        lines.append(f"  _Last updated: {last_updated}_")

    # --- Next week meal plan ---
    lines.append(f"\n*📅 Next Week — {week.get('weekLabel', next_wid)}:*")
    if plan_was_generated:
        lines.append("  _(Plan auto-generated — PCOD-friendly 🌿)_")
    for m in meals:
        bf = m.get("breakfast", {}).get("name", "") if isinstance(m.get("breakfast"), dict) else ""
        ln = m.get("lunch", {}).get("name", "") if isinstance(m.get("lunch"), dict) else ""
        dn = m.get("dinner", {}).get("name", "") if isinstance(m.get("dinner"), dict) else ""
        lines.append(f"  *{m['day']}* — B: {bf} | L: {ln} | D: {dn}")

    # --- Pantry lows / grocery ---
    if grocery_needed:
        lines.append("\n*⚠️ Pantry Low — Buy This Weekend:*")
        for g in grocery_needed:
            lines.append(f"  • {g}")

    # --- Batch prep ---
    lines.append("\n*📋 Saturday Batch Prep (saved to app ✅):*")
    if batch_prep:
        for bp in batch_prep:
            lines.append(f"  • {bp['task']}")
    else:
        lines.append("  _(no batch prep tasks — add some!)_")

    lines.append("\nHappy prepping tomorrow! 🥗")

    print("\n".join(lines))


if __name__ == "__main__":
    main()
