"""Только сервер без окна — для отладки интерфейса в браузере. LOCALAI_DEMO=1 LOCALAI_PORT=8765"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server

_, url = server.start()
print(url, flush=True)
while True:
    time.sleep(60)
