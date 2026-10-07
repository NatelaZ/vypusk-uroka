#!/usr/bin/env python3
"""Подставить в КОНСПЕКТ.html боевые fs.getcourse-URL вместо относительных src="скриншоты/…".

  python3 apply_urls.py --course vaibkoding --lesson 2.2 [--html путь]
Карта берётся из <урок>/скриншоты/_src/gc_urlmap.json. Пустой URL в карте — стоп.
"""
import argparse
import json
import re
import sys
from pathlib import Path

from _lib import Lesson, course, say


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--course"); ap.add_argument("--lesson", required=True); ap.add_argument("--html")
    a = ap.parse_args()
    L = Lesson(course(a.course), a.lesson)
    html_p = Path(a.html) if a.html else L.konspekt
    m = json.loads((L.shots_dir / "_src" / "gc_urlmap.json").read_text(encoding="utf-8"))
    missing = [k for k, v in m.items() if not v]
    if missing:
        sys.exit("нет URL для: " + ", ".join(missing))
    html = html_p.read_text(encoding="utf-8"); n = 0
    for fn, url in m.items():
        old = f'src="скриншоты/{fn}"'; k = html.count(old)
        if k > 1:
            say(f"⚠️ {fn}: {k} вхождений")
        html = html.replace(old, f'src="{url}"'); n += k
    html_p.write_text(html, encoding="utf-8")
    left = re.findall(r'src="скриншоты/[^"]+"', html)
    unused = [fn for fn in m if fn not in html and f'src="{m[fn]}"' not in html]
    say(f"заменено: {n}; осталось относительных: {len(left)}" + (f" {left}" if left else ""))
    if unused:
        say(f"ℹ️ залиты, но в конспекте не используются: {unused}")
    if left:
        sys.exit(1)


if __name__ == "__main__":
    sys.exit(main())
