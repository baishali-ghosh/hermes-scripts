#!/usr/bin/env python3
"""
Telugu Revision Tool — review, quiz, and summarise lessons from Days 1–40 (Phase 1).

Usage:
  py telugu_revise.py --day 5          # Flashcard for a specific day
  py telugu_revise.py --week 3         # Full week review (5 lessons)
  py telugu_revise.py --quiz           # Random quiz (spoiler-hidden answers)
  py telugu_revise.py --quiz --day 12  # Quiz a specific day
  py telugu_revise.py --quiz --week 2  # Quiz entire week (spoilers)
  py telugu_revise.py --random         # Random lesson flashcard
  py telugu_revise.py --summary        # Compact cheatsheet: all 40 days
  py telugu_revise.py --phase          # Phase 1 overview + what you've covered
"""

import sys
import random
import argparse
from pathlib import Path

# ─────────────────────────────────────────────────────
# Import curriculum from main tutor script
# ─────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
from telugu_tutor import CURRICULUM, get_lesson, phase_name

PHASE1_DAYS = 40  # Days 1–40 = Weeks 1–8

# ─────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────

def day_to_week_lesson(day):
    week = ((day - 1) // 5) + 1
    day_in_week = (day - 1) % 5
    return week, day_in_week

def get_all_phase1_lessons():
    """Returns list of (day, week, day_in_week, title, lesson) for days 1–40."""
    result = []
    for day in range(1, PHASE1_DAYS + 1):
        week, day_in_week, title, lesson = get_lesson(day)
        result.append((day, week, day_in_week + 1, title, lesson))
    return result

# ─────────────────────────────────────────────────────
# Formatters
# ─────────────────────────────────────────────────────

def format_flashcard(day, week, day_in_week, title, lesson, label="📖 Review"):
    return f"""🔁 **{label} — Day {day}**
*{phase_name(week)} · Week {week} · Lesson {day_in_week}/5*
**{title}**

**Telugu:**  {lesson['phrase']}
**Speak:**  /{lesson['translit']}/
**Meaning:** {lesson['meaning']}

**Example:**
> {lesson['example']}

💡 **Tip:** {lesson['tip']}"""


def format_quiz_card(day, week, day_in_week, title, lesson):
    """Quiz mode: phrase shown, everything else hidden as Telegram spoilers."""
    return f"""🎯 **Quiz — Day {day}** · Week {week} · {title}

**Telugu:**  {lesson['phrase']}

*Tap the spoilers to reveal →*

**Speak:** ||{lesson['translit']}||
**Meaning:** ||{lesson['meaning']}||
**Example:** ||{lesson['example']}||
💡 **Tip:** ||{lesson['tip']}||"""


def format_week_review(week):
    """Full review of all 5 lessons in a week."""
    topic = CURRICULUM.get(week)
    if not topic:
        return f"❌ Week {week} not found in Phase 1 (weeks 1–8)."

    title = topic["title"]
    lines = [
        f"📚 **Week {week} Review — {title}**",
        f"*{phase_name(week)}*",
        ""
    ]
    for i, lesson in enumerate(topic["lessons"], 1):
        day = (week - 1) * 5 + i
        lines.append(f"**Day {day} — Lesson {i}/5**")
        lines.append(f"• Telugu: {lesson['phrase']}")
        lines.append(f"• Speak: /{lesson['translit']}/")
        lines.append(f"• Meaning: {lesson['meaning']}")
        lines.append(f"• Example: {lesson['example']}")
        lines.append(f"• 💡 {lesson['tip']}")
        lines.append("")

    lines.append("─────────────────────────")
    lines.append(f"✅ That's all 5 lessons from Week {week}. नू'వ్వు చేయగలవు! 🙌")
    return "\n".join(lines)


def format_week_quiz(week):
    """Quiz all 5 lessons in a week with spoilers."""
    topic = CURRICULUM.get(week)
    if not topic:
        return f"❌ Week {week} not found in Phase 1 (weeks 1–8)."

    title = topic["title"]
    lines = [
        f"🎯 **Week {week} Quiz — {title}**",
        f"*Tap spoilers to reveal each answer!*",
        ""
    ]
    for i, lesson in enumerate(topic["lessons"], 1):
        day = (week - 1) * 5 + i
        lines.append(f"**Q{i} (Day {day}):** {lesson['phrase']}")
        lines.append(f"Speak: ||{lesson['translit']}||  Meaning: ||{lesson['meaning']}||")
        lines.append(f"Example: ||{lesson['example']}||")
        lines.append("")

    lines.append("─────────────────────────")
    lines.append(f"🏁 Week {week} quiz done! How many did you get right?")
    return "\n".join(lines)


def format_summary():
    """Compact cheatsheet of all 40 days, one line per lesson."""
    lines = [
        "📋 **Phase 1 Cheatsheet — Days 1–40**",
        "*All 8 weeks at a glance*",
        ""
    ]
    for week in range(1, 9):
        topic = CURRICULUM[week]
        lines.append(f"**Week {week} — {topic['title']}**")
        for i, lesson in enumerate(topic["lessons"], 1):
            day = (week - 1) * 5 + i
            lines.append(
                f"  D{day:02d}· {lesson['phrase']} — {lesson['meaning']}"
            )
        lines.append("")

    lines.append("─────────────────────────")
    lines.append("💪 40 lessons. 8 topics. Phase 1 complete. నువ్వు చేయగలవు!")
    return "\n".join(lines)


def format_phase_overview():
    """Phase 1 overview with week titles and day ranges."""
    week_titles = {w: CURRICULUM[w]["title"] for w in range(1, 9)}
    lines = [
        "🌱 **Phase 1 — Foundation (Days 1–40)**",
        "",
        "8 weeks · 40 lessons · Your complete Telugu starter kit",
        ""
    ]
    for week, title in week_titles.items():
        d_start = (week - 1) * 5 + 1
        d_end = week * 5
        lines.append(f"**Week {week}** (Days {d_start}–{d_end}) — {title}")

    lines.append("")
    lines.append("─────────────────────────")
    lines.append("📖 **How to revise:**")
    lines.append("• *'Telugu quiz'* → random lesson quiz")
    lines.append("• *'Telugu week 3 review'* → full week flashcards")
    lines.append("• *'Telugu week 5 quiz'* → spoiler quiz for a week")
    lines.append("• *'Telugu day 12'* → specific day flashcard")
    lines.append("• *'Telugu summary'* → all 40 in one cheatsheet")
    lines.append("")
    lines.append("Say **'resume Telugu tutor'** when you're ready for Day 41! 🚀")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Telugu Phase 1 Revision Tool")
    parser.add_argument("--day", type=int, help="Specific day (1–40)")
    parser.add_argument("--week", type=int, help="Specific week (1–8)")
    parser.add_argument("--quiz", action="store_true", help="Quiz mode (spoiler answers)")
    parser.add_argument("--random", action="store_true", help="Random lesson flashcard")
    parser.add_argument("--summary", action="store_true", help="Full Phase 1 cheatsheet")
    parser.add_argument("--phase", action="store_true", help="Phase 1 overview")
    args = parser.parse_args()

    # --summary
    if args.summary:
        print(format_summary())
        return

    # --phase overview
    if args.phase:
        print(format_phase_overview())
        return

    # --quiz --week N  (full week quiz)
    if args.quiz and args.week:
        week = args.week
        if week < 1 or week > 8:
            print("❌ Week must be between 1 and 8 for Phase 1 revision.")
            return
        print(format_week_quiz(week))
        return

    # --week N  (full week review)
    if args.week and not args.quiz:
        week = args.week
        if week < 1 or week > 8:
            print("❌ Week must be between 1 and 8 for Phase 1 revision.")
            return
        print(format_week_review(week))
        return

    # --quiz --day N  (single day quiz)
    if args.quiz and args.day:
        day = args.day
        if day < 1 or day > PHASE1_DAYS:
            print(f"❌ Day must be between 1 and {PHASE1_DAYS} for Phase 1 revision.")
            return
        week, day_in_week, title, lesson = get_lesson(day)
        print(format_quiz_card(day, week, day_in_week + 1, title, lesson))
        return

    # --quiz (random)
    if args.quiz:
        day = random.randint(1, PHASE1_DAYS)
        week, day_in_week, title, lesson = get_lesson(day)
        print(format_quiz_card(day, week, day_in_week + 1, title, lesson))
        return

    # --day N  (specific day flashcard)
    if args.day:
        day = args.day
        if day < 1 or day > PHASE1_DAYS:
            print(f"❌ Day must be between 1 and {PHASE1_DAYS} for Phase 1 revision.")
            return
        week, day_in_week, title, lesson = get_lesson(day)
        print(format_flashcard(day, week, day_in_week + 1, title, lesson))
        return

    # --random
    if args.random:
        day = random.randint(1, PHASE1_DAYS)
        week, day_in_week, title, lesson = get_lesson(day)
        print(format_flashcard(day, week, day_in_week + 1, title, lesson, label="🎲 Random Review"))
        return

    # Default: phase overview
    print(format_phase_overview())


if __name__ == "__main__":
    main()
