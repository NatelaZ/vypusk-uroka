#!/usr/bin/env python3
"""Все проверки КОНСПЕКТ.html перед буфером: структура, якоря, ссылки, картинки, стоп-слова, voice-lint, рендер.

  python3 check_konspekt.py --course vaibkoding --lesson 2.2 [--html путь] [--no-render]

Жёсткие (код возврата 1): непарные теги · битые якоря · внешние ссылки без target=_blank rel=noopener ·
относительные src · чужой CSS-префикс · нет iframe Kinescope · нет оглавления до видео · переполнение по ширине ·
обещание из речи видео («под уроком», «на листке», «обещала», «в следующий раз») не сверено в ОБЕЩАНИЯ-ВИДЕО.md,
его куска нет в конспекте или «под уроком» не ведёт из блока ссылок под видео.
Мягкие (предупреждение): слова-запреты курса в тексте, находки voice-lint (кроме капслока в комментариях/именах файлов).
Рендер: Chrome 1440 и 390 → скриншоты в скриншоты/_src/render_*.png — посмотреть глазами.
"""
import argparse
import html as H
import re
import subprocess
import sys
from pathlib import Path

from _lib import Lesson, course, say, shared

FORBIDDEN = [r"\bИИ\b", r"\bсесси[яию]\b", r"\bвчера\b", r"\bсегодня\b", r"\b[Уу]рок \d+\.\d+", r"\bтест\b",
             r"\bлегко\b", r"\bбез усилий\b", r"\bгарантиру"]


# Обещания из речи итогового видео. «Под уроком» — обязано вести из блока ссылок под плеером.
PROMISE_RX = re.compile(r"под\s+урок|под\s+видео|на\s+листк|листок\s+под|в\s+описании|обеща|"
                        r"в\s+следующ\w+\s+(?:раз|урок)|покажу\s+отдельно|разбер[её]м\s+отдельно", re.I)
UNDER_RX = re.compile(r"под\s+урок|под\s+видео|листк|листок|в\s+описании", re.I)
PROMISES_FILE = "ОБЕЩАНИЯ-ВИДЕО.md"
PROMISES_HELP = f"""Файл {PROMISES_FILE} в папке урока — таблица, по строке на каждое найденное место речи:
| Время | Что сказано | Якорь | Кусок текста в конспекте |
|---|---|---|---|
| 01:36 | адрес телеграма в браузере лежит под уроком | #vb6-bot | web.telegram.org |
| 03:05 | «на экране она будет называть её токеном» | - | ложное: не обещание |
Якорь «-» допустим только для мест без «под уроком» (обещание закрыто в тексте или ложное срабатывание
с причиной «ложное: …»). Кусок — дословная подстрока видимого текста конспекта."""


def check_promises(L, html: str, txt: str, bad, say):
    """Каждое обещание из rech_final.txt → строка в ОБЕЩАНИЯ-ВИДЕО.md → якорь и дословный кусок в конспекте."""
    rech = L.final_dir / "rech_final.txt"
    if not rech.exists():
        bad(f"нет {rech} — обещания видео не с чем сверять (сначала transcribe_final.py)")
        return
    found = []
    for ln in rech.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\[(\d\d:\d\d)\]\s*(.*)", ln)
        if m and PROMISE_RX.search(m.group(2)):
            found.append((m.group(1), m.group(2)))
    say(f"обещаний в речи видео: {len(found)}")
    pf = L.lesson_dir / PROMISES_FILE
    if not pf.exists():
        for t, s in found:
            say(f"   [{t}] {s}")
        bad(f"нет {pf.name} — сверка обещаний видео не сделана.\n{PROMISES_HELP}")
        return
    rows = {}
    for ln in pf.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(cells) >= 4 and re.fullmatch(r"\d\d:\d\d", cells[0]):
            rows[cells[0]] = (cells[2], cells[3])
    links = re.search(r'class="[^"]*links[^"]*".*?</ul>', html, flags=re.S)
    links_html = links.group(0) if links else ""
    flat = re.sub(r"\s+", " ", txt)
    ok = 0
    for t, s in found:
        if t not in rows:
            bad(f"обещание [{t}] «{s}» не сверено — нет строки в {pf.name}")
            continue
        anchor, piece = rows[t]
        under = bool(UNDER_RX.search(s))
        if anchor in ("-", "—", ""):
            if under:
                bad(f"[{t}] обещано «под уроком», а якоря нет: «{s}»")
                continue
            if not piece.lower().startswith("ложное") and piece not in flat:
                bad(f"[{t}] кусок «{piece}» не найден в тексте конспекта")
                continue
        else:
            aid = anchor.lstrip("#")
            if f'id="{aid}"' not in html:
                bad(f"[{t}] якоря #{aid} нет в конспекте")
                continue
            if under and f'href="#{aid}"' not in links_html:
                bad(f"[{t}] «под уроком», но в блоке ссылок под видео нет ссылки на #{aid}")
                continue
            start = html.find(f'id="{aid}"')
            nxt = html.find("<section", start + 1)
            sect = visible_text(html[start:nxt if nxt > 0 else len(html)])
            if piece not in re.sub(r"\s+", " ", sect):
                bad(f"[{t}] кусок «{piece}» не найден в секции #{aid}")
                continue
        ok += 1
    if ok == len(found):
        say(f"✓ обещания видео: {ok}/{len(found)} закрыты ({pf.name})")


def visible_text(html: str) -> str:
    s = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    s = re.sub(r"<style.*?</style>", " ", s, flags=re.S)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", H.unescape(s))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--course"); ap.add_argument("--lesson", required=True); ap.add_argument("--html")
    ap.add_argument("--no-render", action="store_true")
    a = ap.parse_args()
    L = Lesson(course(a.course), a.lesson)
    p = Path(a.html) if a.html else L.konspekt
    html = p.read_text(encoding="utf-8"); hard = 0

    def bad(msg):
        nonlocal hard; hard += 1; say("✗ " + msg)

    for t in ("section", "figure", "div", "ul", "ol", "li", "p", "a", "span", "h1", "h2", "h3", "strong", "em"):
        o, c = len(re.findall(rf"<{t}\b", html)), len(re.findall(rf"</{t}>", html))
        if o != c:
            bad(f"тег <{t}>: открыто {o}, закрыто {c}")
    say(f"✓ парность тегов проверена")
    ids = set(re.findall(r'id="([^"]+)"', html)); hrefs = re.findall(r'href="#([^"]+)"', html)
    broken = [x for x in hrefs if x not in ids]
    (bad(f"битые якоря: {broken}") if broken else say(f"✓ якорей {len(hrefs)}, битых 0"))
    ext = re.findall(r"<a [^>]*href=\"http[^>]*>", html)
    nb = [e for e in ext if 'target="_blank"' not in e or 'rel="noopener"' not in e]
    (bad(f"внешние ссылки без новой вкладки: {nb}") if nb else say(f"✓ внешних ссылок {len(ext)}, все в новой вкладке"))
    rel = re.findall(r'src="скриншоты/[^"]+"', html); imgs = re.findall(r"<img ", html)
    (bad(f"относительных src: {len(rel)} — сначала apply_urls.py") if rel else say(f"✓ картинок {len(imgs)}, все абсолютные"))
    foreign = set(re.findall(r"\b(v[km]\d+-)", html)) - {L.prefix}
    (bad(f"чужой префикс CSS: {foreign} (нужен {L.prefix})") if foreign else say(f"✓ префикс {L.prefix}"))
    if "kinescope.io/embed/" not in html:
        bad("нет iframe Kinescope")
    else:
        say("✓ iframe Kinescope есть")
    toc = html.find("toc"); vid = html.find("kinescope.io/embed/")
    (bad("оглавление должно стоять ДО видео") if not (0 < toc < vid) else say("✓ оглавление до видео"))
    txt = visible_text(html)
    for rx in FORBIDDEN:
        hits = re.findall(rx, txt)
        if hits:
            say(f"⚠️ слово-запрет «{hits[0]}» ×{len(hits)} — проверь контекст")
    check_promises(L, html, txt, bad, say)
    say(f"размер: {len(html.encode()) // 1024} КБ, видимого текста {len(txt) // 1000} тыс. знаков")

    lint = shared("voice_lint")
    r = subprocess.run(["node", str(lint), str(p)], capture_output=True, text=True)
    lines = [ln for ln in (r.stdout + r.stderr).splitlines() if ln.startswith("строка") and "капслок" not in ln]
    say(f"voice-lint: {len(lines)} находок без капслока" + (":" if lines else ""))
    for ln in lines[:15]:
        say("   " + ln)

    if not a.no_render:
        from playwright.sync_api import sync_playwright
        out = L.shots_dir / "_src"; out.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as pw:
            br = pw.chromium.launch()
            for name, w, h in (("desktop", 1440, 900), ("mobile", 390, 844)):
                pg = br.new_page(viewport={"width": w, "height": h})
                pg.goto("file://" + str(p.resolve()), wait_until="networkidle", timeout=120000)
                pg.wait_for_timeout(1500)
                sw, cw, sh = pg.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth, document.documentElement.scrollHeight]")
                loaded = pg.evaluate("Array.from(document.images).filter(i=>i.naturalWidth>0).length")
                (bad(f"{name}: горизонтальное переполнение {sw}>{cw}") if sw > cw else
                 say(f"✓ {name}: ширина {cw}, высота {sh}, картинок загрузилось {loaded}/{len(imgs)}"))
                if loaded < len(imgs):
                    say(f"⚠️ {name}: не все картинки загрузились")
                for tag, y in (("top", 0), ("mid", int(sh * 0.45)), ("end", max(0, sh - h))):
                    pg.evaluate(f"window.scrollTo(0,{y})"); pg.wait_for_timeout(300)
                    pg.screenshot(path=str(out / f"render_{name}_{tag}.png"))
            br.close()
        say(f"рендеры: {out}/render_*.png — посмотри глазами top/mid/end")
    say(("✓ ЖЁСТКИХ ОШИБОК НЕТ" if not hard else f"✗ жёстких ошибок: {hard}"))
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
