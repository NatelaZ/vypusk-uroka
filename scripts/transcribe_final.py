#!/usr/bin/env python3
"""Расшифровать ИТОГОВЫЙ файл урока (точка истины) и сравнить с монтажной расшифровкой.

  python3 transcribe_final.py --course vaibkoding --lesson 2.2 --file ~/Downloads/"Вайбкодинг 2.2.mp4"

Кладёт в Монтаж/output/<урок>/final/: audio_final.m4a, transcript_final.json, rech_final.txt.
Расшифровка — чанками по паузам (иначе whisper на длинной дорожке уходит в петлю).
В конце — сверка с output/<урок>/transcript.json: длительности, слова, что вырезано.
"""
import argparse
import difflib
import json
import re
import subprocess
import sys

from _lib import Lesson, course, say, shared


def words(segments):
    return re.findall(r"[а-яёa-z0-9]+", " ".join(s["text"] for s in segments).lower())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--course"); ap.add_argument("--lesson", required=True)
    ap.add_argument("--file", required=True, help="итоговый файл Натэлы (mp4)")
    ap.add_argument("--force", action="store_true", help="пересчитать, даже если transcript_final.json есть")
    a = ap.parse_args()
    L = Lesson(course(a.course), a.lesson)
    mont = shared("montage_root")
    L.final_dir.mkdir(parents=True, exist_ok=True)
    audio = L.final_dir / "audio_final.m4a"
    out = L.final_dir / "transcript_final.json"

    if out.exists() and not a.force:
        say(f"уже есть {out} — пропускаю расшифровку (--force, чтобы пересчитать)")
    else:
        say("аудио → " + audio.name)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", a.file, "-vn", "-c:a", "aac",
                        "-b:a", "160k", str(audio)], check=True)
        say("whisper чанками по паузам (несколько минут)…")
        subprocess.run([str(mont / ".venv/bin/python"), "scripts/_transcribe_chunked.py",
                        "--audio", str(audio), "--out", str(out)], cwd=mont, check=True)

    fin = json.loads(out.read_text(encoding="utf-8"))
    lines = [f"[{int(s['start'])//60:02d}:{int(s['start'])%60:02d}] {s['text']}" for s in fin["segments"]]
    (L.final_dir / "rech_final.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    say(f"✓ {out.name}: {len(fin['segments'])} сегм., {fin['audio_duration']:.1f} с → rech_final.txt")

    src = L.montage_dir / "transcript.json"
    if not src.exists():
        say("монтажной расшифровки нет — сравнивать не с чем"); return
    mon = json.loads(src.read_text(encoding="utf-8"))
    wm, wf = words(mon["segments"]), words(fin["segments"])
    say(f"\nсверка с монтажом: {mon.get('audio_duration', 0):.1f} с / {len(wm)} слов  →  "
        f"итог {fin['audio_duration']:.1f} с / {len(wf)} слов")
    sm = difflib.SequenceMatcher(a=wm, b=wf, autojunk=False)
    cut = [(i1, i2) for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag in ("delete", "replace") and i2 - i1 >= 6]
    if not cut:
        say("✓ смысловых вырезов не найдено (расхождения ≤5 слов — ослышки whisper): вырезаны только паузы")
    else:
        say(f"⚠️ в итоге отсутствуют куски монтажной речи ({len(cut)}):")
        for i1, i2 in cut[:20]:
            say("   — " + " ".join(wm[i1:i2])[:160])


if __name__ == "__main__":
    sys.exit(main())
