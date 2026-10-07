"""Общее для скриптов выпуска урока: конфиг курсов, разбор номера урока, пути."""
import re
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
KURSY = SKILL.parents[2]          # vypusk-uroka → skills → .claude → Курсы


def _x(p) -> Path:
    return Path(str(p)).expanduser()


def load_cfg() -> dict:
    return yaml.safe_load((SKILL / "courses.yaml").read_text(encoding="utf-8"))


def shared(key: str) -> Path:
    return _x(load_cfg()["shared"][key])


def course(key: str | None = None) -> dict:
    """Курс по ключу; без ключа — по текущей папке (cwd внутри Курсы/<dir>)."""
    cfg = load_cfg()["courses"]
    if key:
        if key not in cfg:
            sys.exit(f"нет курса «{key}» в courses.yaml; есть: {', '.join(cfg)}")
        c = dict(cfg[key]); c["key"] = key
    else:
        cwd = Path.cwd().resolve()
        hit = [(k, v) for k, v in cfg.items() if (KURSY / v["dir"]).resolve() in (cwd, *cwd.parents)]
        if not hit:
            sys.exit("не понял курс по текущей папке — передай --course " + "|".join(cfg))
        k, v = hit[0]; c = dict(v); c["key"] = k
    c["root"] = KURSY / c["dir"]
    return c


class Lesson:
    """«2.2» → module 2, num 2, dash «2-2», префикс CSS, папки.

    Модуль может быть буквой — бонус-блоки нумеруются «Б.2», «Б.11».
    """

    def __init__(self, c: dict, lesson: str):
        # Урок-вставка с буквой («4.6б»): в названиях и папках — кириллицей, в CSS и путях монтажа — латиницей (vm46b-, vaib-4-6b).
        m = re.fullmatch(r"([\dA-Za-zА-Яа-я]+?)[.\-](\d+)([a-zа-я]?)", lesson.strip())
        if not m:
            sys.exit(f"номер урока ожидается как 2.2, Б.2 или 4.6б, получил «{lesson}»")
        self.c = c
        mod = m.group(1)
        self.module = int(mod) if mod.isdigit() else mod.upper()
        self.num = int(m.group(2))
        sfx = m.group(3)
        sfx_lat = sfx.translate(str.maketrans("абвгд", "abvgd"))
        self.dot = f"{self.module}.{self.num}{sfx}"
        self.dash = f"{self.module}-{self.num}{sfx}"
        num = f"{self.num}{sfx_lat}" if sfx else self.num
        self.fmt = dict(module=self.module, num=num, dash=self.dash, dot=self.dot)
        self.prefix = c["css_prefix"].format(**self.fmt)
        self.title = c["kinescope_title"].format(**self.fmt)
        self.montage_dir = shared("montage_root") / c["montage_output"].format(**self.fmt)
        self.final_dir = self.montage_dir / "final"
        self.lessons_dir = c["root"] / c["lessons_dir"].format(**self.fmt)

    @property
    def lesson_dir(self) -> Path:
        pat = self.c.get("lesson_dir_glob", "{dot}-*").format(**self.fmt)
        hits = sorted(self.lessons_dir.glob(pat)) if self.lessons_dir.exists() else []
        if not hits:
            sys.exit(f"папка урока {pat} не найдена в {self.lessons_dir} — создай её "
                     f"(например «{self.dot}-polka»)")
        return hits[0]

    @property
    def slug(self) -> str:
        return self.lesson_dir.name

    @property
    def shots_dir(self) -> Path:
        return self.lesson_dir / "скриншоты"

    @property
    def konspekt(self) -> Path:
        return self.lesson_dir / "КОНСПЕКТ.html"


def kinescope_key() -> str:
    return yaml.safe_load(shared("kinescope_config").read_text())["kinescope_api_key"]


def say(msg: str):
    print(msg, flush=True)
