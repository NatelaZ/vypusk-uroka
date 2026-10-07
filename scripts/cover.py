#!/usr/bin/env python3
"""Обложка урока одной командой: запись в план → портрет (Визуал) → рендер → постер на Kinescope → снимок плеера.

  python3 cover.py --course vaibkoding --lesson 2.2 --video-id 4TgwgDQpi5DEJsqoZeZ8aJ \
      --title "Опись, а не код" --sub "Откуда берут готовые системы — и как забрать одну словами"
  python3 cover.py ... --pairs                 # показать свободные пары «одежда+поза»
  python3 cover.py ... --wardrobe rubashka --pose ruki-na-poyase   # выбрать пару руками
  python3 cover.py ... --no-upload             # только сделать PNG, на Kinescope не ставить

Пара «одежда+поза» подбирается автоматически из НЕ занятых (правило: на каждой обложке новая пара).
Тема — из courses.yaml (весь Вайбкодинг светлый). Запускать системным python3 (нужен PIL).
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from _lib import Lesson, course, say, shared


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--course"); ap.add_argument("--lesson", required=True)
    ap.add_argument("--video-id"); ap.add_argument("--title"); ap.add_argument("--sub", default="")
    ap.add_argument("--wardrobe"); ap.add_argument("--pose"); ap.add_argument("--theme")
    ap.add_argument("--pairs", action="store_true", help="только показать свободные пары")
    ap.add_argument("--no-upload", action="store_true")
    a = ap.parse_args()
    c = course(a.course); L = Lesson(c, a.lesson)
    covers = c["root"] / c["covers_dir"]
    sys.path.insert(0, str(covers / "scripts"))
    import make_all                      # noqa: E402  (gen_plate, fit_fs, plate_path)
    from briefs import POSES, WARDROBE   # noqa: E402
    from render_cover import render      # noqa: E402

    plan_path = covers / "план-обложек.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    used = {(x["wardrobe"], x["pose"]) for x in plan["covers"]}
    wc = {w: sum(1 for x in plan["covers"] if x["wardrobe"] == w) for w in WARDROBE}
    pc = {p: sum(1 for x in plan["covers"] if x["pose"] == p) for p in POSES}
    free = sorted(((w, p) for w in WARDROBE for p in POSES if (w, p) not in used),
                  key=lambda x: (wc[x[0]] + pc[x[1]], x))
    if a.pairs:
        say(f"занято пар: {len(used)}, свободно: {len(free)}; самые редкие:")
        for w, p in free[:15]:
            say(f"  {w:24} {p:24} (одежда ×{wc[w]}, поза ×{pc[p]})")
        return
    if not (a.video_id and a.title):
        sys.exit("нужны --video-id и --title (и --sub)")

    wardrobe, pose = (a.wardrobe, a.pose) if (a.wardrobe and a.pose) else free[0]
    if (wardrobe, pose) in used and not (a.wardrobe and a.pose):
        sys.exit("свободных пар нет — добавь одежду/позу в briefs.py")
    if (wardrobe, pose) in used:
        say(f"⚠️ пара {wardrobe}+{pose} уже была на другой обложке — правило «каждый раз новая» нарушено")
    theme = a.theme or c.get("cover_theme", "light")
    entry = {"id": a.video_id, "lesson": L.slug, "chip": c["cover_chip"].format(**L.fmt),
             "eyebrow": c["cover_eyebrow"].format(**L.fmt), "theme": theme,
             "title": a.title, "sub": a.sub, "wardrobe": wardrobe, "pose": pose}
    ids = [x["id"] for x in plan["covers"]]
    if a.video_id in ids:
        plan["covers"][ids.index(a.video_id)] = entry
    else:
        plan["covers"].append(entry)
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    say(f"план: {entry['chip']} · {theme} · {wardrobe} + {pose} · «{a.title}» (записей {len(plan['covers'])})")

    say("портрет через Визуал (если ещё нет — 1–2 минуты)…")
    key, ok, msg = make_all.gen_plate(entry)
    if not ok:
        sys.exit(f"портрет не сделан: {msg}")
    say(f"  {key}: {msg}")
    tmp = covers / "плашки" / "_probe"; tmp.mkdir(parents=True, exist_ok=True)
    fs, shrunk = make_all.fit_fs(entry, tmp)
    out = covers / "готовые" / f"{L.slug}__{a.video_id}.png"
    render(theme, str(make_all.plate_path(entry)), entry["chip"], a.title, a.sub, str(out), fs=fs,
           eyebrow=entry["eyebrow"])
    say(f"✓ обложка: {out} (кегль {fs}{', уменьшен под кнопку' if shrunk else ''})")
    if a.no_upload:
        return
    r = subprocess.run([sys.executable, str(covers / "scripts/upload_posters.py"), "--only", a.video_id],
                       capture_output=True, text=True)
    say(r.stdout.strip() or r.stderr.strip())
    if r.returncode:
        sys.exit("постер не встал")
    time.sleep(6)
    snap = covers / "проверка" / f"player_{L.dot}.png"
    subprocess.run([str(shared("chrome")), "--headless", "--disable-gpu", "--hide-scrollbars",
                    "--window-size=1280,720", "--virtual-time-budget=10000", f"--screenshot={snap}",
                    f"https://kinescope.io/embed/{a.video_id}"], capture_output=True)
    say(f"✓ снимок живого плеера: {snap} — ПОСМОТРИ ГЛАЗАМИ (кнопка «плей» не на тексте?)")


if __name__ == "__main__":
    sys.exit(main())
