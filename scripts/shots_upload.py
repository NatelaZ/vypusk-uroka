#!/usr/bin/env python3
"""Скриншоты урока: привести к 1720 px JPEG q90, собрать контактный лист, залить на fs.getcourse, записать карту URL.

  python3 shots_upload.py --course vaibkoding --lesson 2.2 --from <папка с кадрами> --contact-sheet --dry
  python3 shots_upload.py --course vaibkoding --lesson 2.2            # залить то, что лежит в скриншоты/

--from: папка с исходными кадрами (png/jpg), имена уже как надо: <prefix>NN-slug.*;
        они пережмутся в <урок>/скриншоты/<prefix>NN-slug.jpg. Без --from берутся готовые jpg.
--contact-sheet: скриншоты/_src/contact_N.png — посмотреть глазами на личные данные ДО заливки.
--dry: ничего не заливать. Карта — скриншоты/_src/gc_urlmap.json.
--reuse-hashes: не заливать заново файлы, чей хэш уже записан в скриншоты/_src/gc_hashes.json
Если страница адреса не открылась трижды — адрес собирается из хэша (sc/0) и сверяется байтами на fs.getcourse.ru.
        (хэши пишутся сразу после фазы заливки — обрыв на фазе чтения адресов не стоит повторной заливки).
--resolve host=ip: обойти сломанный DNS (правило host-resolver для Chromium), напр. school.ru=203.0.113.10.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

from _lib import Lesson, course, say

BLOCK = ("domfox", "yandex", "google-analytics", "googletagmanager", "vk.com", "facebook", "jivo",
         "carrotquest", "top-fwz")


def normalize(src_dir: Path, dst: Path, prefix: str) -> list:
    from PIL import Image
    out = []
    for p in sorted(src_dir.iterdir()):
        if not p.name.startswith(prefix) or p.suffix.lower() not in (".png", ".jpg", ".jpeg"):
            continue
        im = Image.open(p).convert("RGB")
        if im.width != 1720:
            im = im.resize((1720, round(im.height * 1720 / im.width)), Image.LANCZOS)
        f = dst / (p.stem + ".jpg")
        im.save(f, "JPEG", quality=90, optimize=True, progressive=True)
        out.append(f); say(f"  {f.name:52} {f.stat().st_size // 1024} КБ")
    return out


def contact_sheet(files: list, dst: Path):
    from PIL import Image, ImageDraw, ImageFont
    W, H, COLS, PAD, PER = 480, 270, 4, 34, 16
    font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 20)
    for si in range(0, len(files), PER):
        chunk = files[si:si + PER]; rows = (len(chunk) + COLS - 1) // COLS
        sheet = Image.new("RGB", (COLS * W, rows * (H + PAD)), "white"); d = ImageDraw.Draw(sheet)
        for i, p in enumerate(chunk):
            x, y = (i % COLS) * W, (i // COLS) * (H + PAD)
            sheet.paste(Image.open(p).convert("RGB").resize((W, H)), (x, y + PAD))
            d.text((x + 6, y + 6), p.stem[:40], fill="black", font=font)
        f = dst / f"contact_{si // PER + 1}.png"; sheet.save(f); say(f"  контактный лист: {f}")


def upload(files: list, c: dict, outmap: Path, reuse: bool = False, resolve: str = ""):
    from playwright.sync_api import sync_playwright
    state = c["root"] / c["gc_state"]; acc = c["gc_account"]
    hashes_path = outmap.parent / "gc_hashes.json"
    known = json.loads(hashes_path.read_text(encoding="utf-8")) if (reuse and hashes_path.exists()) else {}
    result, urlmap = {}, {}
    args = [f"--host-resolver-rules=MAP {resolve.split('=')[0]} {resolve.split('=')[1]}"] if resolve else []
    with sync_playwright() as p:
        br = p.chromium.launch(headless=True, args=args)
        ctx = br.new_context(storage_state=str(state), viewport={"width": 1500, "height": 1000}, locale="ru-RU")
        ctx.route("**/*", lambda r: r.abort() if any(b in r.request.url for b in BLOCK) else r.continue_())
        pg = ctx.new_page(); last = {"v": None}

        def on_resp(r):
            if r.request.method == "POST" and "secure-direct-upload" in r.url and r.status == 200:
                try:
                    b = r.text().strip()
                    if re.fullmatch(r"[0-9a-f]{32}\.(jpe?g|png)", b):
                        last["v"] = b
                except Exception:
                    pass
        pg.on("response", on_resp)
        for i, f in enumerate(files, 1):
            if known.get(f.name):
                result[f.name] = known[f.name]; say(f"  [{i}/{len(files)}] {f.name} -> {known[f.name]} (хэш из gc_hashes.json)")
                continue
            last["v"] = None
            pg.goto(c["gc_fileindex"], wait_until="commit", timeout=120000)
            for _ in range(60):
                if pg.locator("input[type=file]").count():
                    break
                pg.wait_for_timeout(500)
            else:
                sys.exit("⚠️ поле загрузки не появилось — сессия админки протухла? перелогинься и перезапиши _gc_state.json")
            pg.wait_for_timeout(800)
            pg.locator("input[type=file]").first.set_input_files(str(f))
            for _ in range(60):
                if last["v"]:
                    break
                pg.wait_for_timeout(500)
            result[f.name] = last["v"]; say(f"  [{i}/{len(files)}] {f.name} -> {last['v']}")
        # хэши — на диск сразу: обрыв сети на фазе адресов не должен стоить повторной заливки
        old_h = json.loads(hashes_path.read_text(encoding="utf-8")) if hashes_path.exists() else {}
        old_h.update({k: v for k, v in result.items() if v})
        hashes_path.write_text(json.dumps(old_h, ensure_ascii=False, indent=1), encoding="utf-8")
        by_name = {f.name: f for f in files}
        vp = ctx.new_page()
        view_base = c["gc_fileindex"].rsplit("/file/", 1)[0] + "/file/view?hash="
        for fn, h in result.items():
            if not h:
                urlmap[fn] = ""; continue
            m = None
            for attempt in range(3):
                try:
                    vp.goto(view_base + h, wait_until="commit", timeout=60000)
                except Exception as e:
                    say(f"  ⚠️ {fn}: страница адреса не открылась (попытка {attempt + 1}/3): {str(e).splitlines()[0][:90]}")
                    continue
                for _ in range(40):
                    m = re.search(rf"https://fs\.getcourse\.ru/fileservice/file/download/a/{acc}/sc/\d+/h/{re.escape(h)}", vp.content())
                    if m:
                        break
                    vp.wait_for_timeout(500)
                if m:
                    break
            if not m:
                # хост школы лёг, а fs.getcourse.ru живой: он отдаёт файл по хэшу с любым sc/N (2.3, 26.08) —
                # собираем адрес с sc/0 и принимаем его только если байты совпали с локальным файлом
                cand = f"https://fs.getcourse.ru/fileservice/file/download/a/{acc}/sc/0/h/{h}"
                try:
                    import hashlib, urllib.request
                    body = urllib.request.urlopen(cand, timeout=60).read()
                    if hashlib.md5(body).hexdigest() == hashlib.md5(by_name[fn].read_bytes()).hexdigest():
                        say(f"  ↪ {fn}: адрес собран из хэша (sc/0), байты сверены с fs.getcourse.ru")
                        urlmap[fn] = cand; continue
                    say(f"  ⚠️ {fn}: fs.getcourse.ru отдал другой файл по sc/0 — адрес не записан")
                except Exception as e:
                    say(f"  ⚠️ {fn}: запасной путь через fs.getcourse.ru не сработал: {str(e)[:90]}")
            urlmap[fn] = m.group(0) if m else ""
        br.close()
    old = json.loads(outmap.read_text(encoding="utf-8")) if outmap.exists() else {}
    old.update(urlmap)
    outmap.write_text(json.dumps(old, ensure_ascii=False, indent=1), encoding="utf-8")
    ok = sum(1 for v in urlmap.values() if v)
    say(f"✓ залито {ok}/{len(files)} → {outmap}" + ("" if ok == len(files) else "  ⚠️ есть пустые URL — перезапусти"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--course"); ap.add_argument("--lesson", required=True)
    ap.add_argument("--from", dest="src", help="папка с исходными кадрами")
    ap.add_argument("--contact-sheet", action="store_true"); ap.add_argument("--dry", action="store_true")
    ap.add_argument("--reuse-hashes", action="store_true", help="не заливать файлы с уже известным хэшем")
    ap.add_argument("--resolve", default="", help="host=ip — обойти сломанный DNS (Chromium host-resolver)")
    a = ap.parse_args()
    c = course(a.course); L = Lesson(c, a.lesson)
    dst = L.shots_dir; dst.mkdir(exist_ok=True); (dst / "_src").mkdir(exist_ok=True)
    if a.src:
        say(f"пережимаю кадры из {a.src} → {dst} (префикс {L.prefix}):")
        files = normalize(Path(a.src).expanduser(), dst, L.prefix)
    else:
        files = sorted(p for p in dst.glob(f"{L.prefix}*.jpg"))
    if not files:
        sys.exit(f"нет файлов {L.prefix}*.jpg в {dst}")
    say(f"скриншотов: {len(files)}")
    if a.contact_sheet:
        contact_sheet(files, dst / "_src")
    if a.dry:
        say("--dry: заливка пропущена"); return
    upload(files, c, dst / "_src" / "gc_urlmap.json", reuse=a.reuse_hashes, resolve=a.resolve)


if __name__ == "__main__":
    sys.exit(main())
