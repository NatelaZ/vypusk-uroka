"""Запуск любого скрипта Kinescope с прибитыми живыми IP — обход VPN-дыры в DNS-пуле.

  python3 scripts/pin_kinescope.py scripts/kinescope_upload.py --course … --lesson … --file …
  python3 scripts/pin_kinescope.py scripts/cover.py --lesson … --video-id …

Зачем: api.kinescope.io резолвится то в 46.102.104.4 (живой), то в 193.238.47.254 — через VPN
второй даёт ConnectTimeout, хотя ping идёт и порт 443 открыт. Выглядит как «API Kinescope лежит».
Каждому хосту — СВОЙ адрес: прибить загрузчик к IP api — получить 413 Request Entity Too Large.
Адреса проверять curl --resolve, если снова перестанет ходить (грабли.md, раздел Kinescope)."""
import socket, sys, runpy, os

PIN = {"api.kinescope.io": "46.102.104.4", "uploader.kinescope.io": "46.102.104.5"}
_orig = socket.getaddrinfo

def getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    ip = PIN.get(host)
    if ip:
        return _orig(ip, port, family, type, proto, flags)
    return _orig(host, port, family, type, proto, flags)

socket.getaddrinfo = getaddrinfo
script = sys.argv[1]
sys.path.insert(0, os.path.dirname(os.path.abspath(script)))
sys.argv = sys.argv[1:]
runpy.run_path(script, run_name="__main__")
