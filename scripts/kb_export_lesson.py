#!/usr/bin/env python3
"""Выгрузить урок в базу знаний ПОСЛЕ приёмки Натэлой — с правильным заголовком и по итоговой расшифровке.

  python3 kb_export_lesson.py --course vaibkoding --lesson 2.2 --summary-file kratko.md --theses-file tezisy.md \
      --topics "вайб-кодинг, github, репозиторий" [--dry]

Чинит две грабли голого kb_export.py: заголовок берётся из courses.yaml (а не из первого mp4 —
«base_slides»), расшифровка — final/transcript_final.json (точка истины), а оглавление по слайдам
пересчитывается на тайминги итогового файла. «Кратко» и тезисы пишет Claude (файлы: summary — абзац,
theses — по строке на тезис, маркер «- » необязателен).
"""
import argparse
import difflib
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

from _lib import Lesson, course, say, shared


def remap(t: float, mon: list, fin: list) -> float:
    """Время монтажной дорожки → время итогового файла (по совпадению текста сегментов)."""
    i = max((k for k, s in enumerate(mon) if s["start"] <= t), default=0)
    lo, hi = max(0, i - 40), min(len(fin), i + 40)
    best, j = 0.0, None
    for k in range(lo, hi):
        r = difflib.SequenceMatcher(a=mon[i]["text"].lower(), b=fin[k]["text"].lower()).ratio()
        if r > best:
            best, j = r, k
    if j is None or best < 0.5:
        return t
    return fin[j]["start"] + max(0.0, t - mon[i]["start"])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--course"); ap.add_argument("--lesson", required=True)
    ap.add_argument("--summary-file", required=True); ap.add_argument("--theses-file", required=True)
    ap.add_argument("--topics", default=""); ap.add_argument("--title"); ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    c = course(a.course); L = Lesson(c, a.lesson)
    sys.path.insert(0, str(shared("montage_root") / "scripts"))
    from kb_export import build_outline, build_transcript, render_markdown  # noqa: E402

    d = L.montage_dir
    fin_p = L.final_dir / "transcript_final.json"
    mon_p = d / "transcript.json"
    tr = json.loads((fin_p if fin_p.exists() else mon_p).read_text(encoding="utf-8"))
    src_note = "final/transcript_final.json" if fin_p.exists() else "transcript.json"
    timing = json.loads((d / "timing.json").read_text(encoding="utf-8")) if (d / "timing.json").exists() else []
    slides = json.loads((d / "slides.json").read_text(encoding="utf-8")) if (d / "slides.json").exists() else []
    if fin_p.exists() and mon_p.exists() and timing:
        mon = json.loads(mon_p.read_text(encoding="utf-8"))["segments"]
        timing = [{**t, "start": remap(float(t["start"]), mon, tr["segments"])} for t in timing]
    summary = Path(a.summary_file).read_text(encoding="utf-8").strip()
    theses = [ln.strip().lstrip("-• ").strip() for ln in Path(a.theses_file).read_text(encoding="utf-8").splitlines() if ln.strip()]
    topics = [t.strip() for t in a.topics.split(",") if t.strip()] or ["урок"]
    made = date.today().isoformat()
    title = a.title or L.title
    entry = {
        "id": c["kb_id"].format(date=made, **L.fmt),
        "front": {"title": title, "type": "урок", "date": made, "course": c["kb_course"], "topics": topics,
                  "added": made, "source": str(fin_p.relative_to(shared("montage_root")) if fin_p.exists() else mon_p.relative_to(shared("montage_root")))},
        "summary": summary, "theses": theses,
        "outline": build_outline(slides, timing), "transcript": build_transcript(tr.get("segments", [])),
    }
    md = render_markdown(entry)
    out = (L.final_dir if fin_p.exists() else d) / "kb_entry.md"
    say(f"{title} → {entry['id']} · расшифровка: {src_note} · {len(md) // 1000} тыс. знаков · тезисов {len(theses)}")
    if a.dry:
        say(md[:1500]); return
    out.write_text(md, encoding="utf-8")
    kb = shared("kb_cli")
    r = subprocess.run([str(kb), "add", str(out), "--on-duplicate", "update"], capture_output=True, text=True)
    say(r.stdout.strip() or r.stderr.strip())
    if r.returncode:
        sys.exit("kb add не принял материал")
    subprocess.run([str(kb), "reindex"], capture_output=True, text=True)
    say(f"✓ в базе знаний; проверить: kb search \"<фраза из урока>\"")


if __name__ == "__main__":
    sys.exit(main())
