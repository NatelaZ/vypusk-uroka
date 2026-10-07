#!/usr/bin/env python3
"""Залить видео урока в проект Kinescope КУРСА (проект берётся из courses.yaml, не из дефолта конфига).

  python3 kinescope_upload.py --course vaibkoding --lesson 2.2 --file ~/Downloads/"Вайбкодинг 2-2.mp4"
  python3 kinescope_upload.py --status 4TgwgDQpi5DEJsqoZeZ8aJ        # проверить видео (транскод, длительность)
  python3 kinescope_upload.py --replace 4TgwgDQpi5DEJsqoZeZ8aJ --file "мастер.mp4"   # мастер поверх 720p, id и ссылки те же

Печатает play/embed-ссылки и UUID, сверяет items_count проекта до/после (ловит мусорные записи
после обрыва сети), ждёт транскод и проверяет, что длительность сошлась с файлом.
"""
import argparse
import json
import subprocess
import sys
import time

import requests

from _lib import Lesson, course, kinescope_key, say

API = "https://api.kinescope.io/v1"
UPLOADER = "https://uploader.kinescope.io/v2/video"


def probe(path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1", path], capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def video(h, vid):
    return requests.get(f"{API}/videos/{vid}", headers=h, timeout=60).json()["data"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--course"); ap.add_argument("--lesson")
    ap.add_argument("--file"); ap.add_argument("--title", help="по умолчанию из courses.yaml")
    ap.add_argument("--status", help="только показать состояние видео по id/uuid")
    ap.add_argument("--replace", help="залить файл ПОВЕРХ существующего видео (id/uuid) — ссылки и обложка сохраняются")
    ap.add_argument("--no-wait", action="store_true")
    a = ap.parse_args()
    h = {"Authorization": f"Bearer {kinescope_key()}"}

    if a.status:
        d = video(h, a.status)
        say(json.dumps({k: d.get(k) for k in ("id", "title", "status", "duration", "play_link", "embed_link")},
                       ensure_ascii=False, indent=1))
        say("качества: " + ", ".join(x.get("quality", "?") for x in d.get("assets", [])))
        return
    if a.replace:
        if not a.file:
            sys.exit("нужен --file вместе с --replace")
        was = video(h, a.replace)
        wq = [x.get("quality") for x in was.get("assets", [])]
        say(f"замена «{was.get('title')}»: сейчас {wq}, длительность {float(was.get('duration') or 0):.2f}")
        want = probe(a.file)
        if abs(float(was.get("duration") or 0) - want) > 2:
            sys.exit(f"⚠️ длительности расходятся ({want:.2f} у файла) — это другой ролик, замена отменена")
        t0 = time.time()
        with open(a.file, "rb") as f:
            r = requests.post(UPLOADER, headers={**h, "X-Parent-ID": was.get("project_id") or "",
                                                 "X-Replace-Video-ID": a.replace,
                                                 "X-Video-Title": "replace"},   # только latin-1: кириллица в заголовке рвёт запрос
                              data=f, timeout=7200)
        if r.status_code != 200:
            sys.exit(f"замена не прошла: HTTP {r.status_code} {r.text[:300]}")
        say(f"файл принят за {round(time.time() - t0)} с, ждём транскод")
        if was.get("title"):   # заголовок был латинским — возвращаем прежнее название
            requests.patch(f"{API}/videos/{a.replace}", headers=h, json={"title": was["title"]}, timeout=60)
        for _ in range(120):
            v = video(h, a.replace); st = v.get("status")
            q = [x.get("quality") for x in v.get("assets", [])]
            say(f"  status={st} duration={float(v.get('duration') or 0):.2f} assets={q}")
            if st == "done":
                say(("✓" if "1080p" in q else "⚠️ по-прежнему нет 1080p") + f" качества: {q}")
                say(f"✓ id прежний: {a.replace} — ссылки в конспектах менять не надо")
                return
            time.sleep(20)
        say("⚠️ транскод не завершился — проверь --status позже")
        return
    if not (a.lesson and a.file):
        sys.exit("нужны --lesson и --file (или --status <id>)")

    c = course(a.course); L = Lesson(c, a.lesson)
    project = c["kinescope_project"]; title = a.title or L.title

    def items():
        return requests.get(f"{API}/projects/{project}", headers=h, timeout=60).json()["data"].get("items_count")

    before = items(); say(f"проект «{c['name']}» {project}: items_count до = {before}")
    t0 = time.time()
    with open(a.file, "rb") as f:
        r = requests.post(UPLOADER, headers={**h, "X-Parent-ID": project, "X-Video-Title": "upload"},
                          data=f, timeout=3600)
    if r.status_code != 200:
        sys.exit(f"заливка не прошла: HTTP {r.status_code} {r.text[:300]}\n"
                 f"⚠️ проверь items_count проекта — обрыв оставляет мусорную запись (status suspended, duration 0), её надо удалить")
    d = r.json()["data"]; vid = d["id"]
    requests.patch(f"{API}/videos/{vid}", headers=h, json={"title": title}, timeout=60).raise_for_status()
    after = items()
    play = d.get("play_link") or f"https://kinescope.io/{vid}"
    short = play.rsplit("/", 1)[-1]
    say(json.dumps({"video_uuid": vid, "short_id": short, "play_link": play,
                    "embed": f"https://kinescope.io/embed/{short}", "title": title,
                    "upload_s": round(time.time() - t0)}, ensure_ascii=False, indent=1))
    say(f"items_count после = {after}" + ("" if after == before + 1 else "  ⚠️ ожидалось +1 — есть мусорные записи?"))
    if a.no_wait:
        return
    want = probe(a.file)
    for _ in range(90):
        v = video(h, vid); st = v.get("status"); dur = float(v.get("duration") or 0)
        q = [x.get("quality") for x in v.get("assets", [])]
        say(f"  status={st} duration={dur:.2f} assets={q}")
        if st == "done":
            ok = abs(dur - want) < 0.5
            say(("✓" if ok else "⚠️") + f" длительность на Kinescope {dur:.2f} vs файл {want:.2f}")
            say(("✓" if "1080p" in q else "⚠️ нет 1080p") + f" качества: {q}")
            return
        time.sleep(20)
    say("⚠️ транскод не завершился за 30 минут — проверь --status позже")


if __name__ == "__main__":
    sys.exit(main())
