"""Dev-режим: запуск бота с автоперезапуском при изменении исходников.

Используется в docker-compose.dev.yml, где ./src примонтирована в контейнер:
правишь код на хосте — процесс бота перезапускается сам, пересобирать
образ и рестартовать compose не нужно.
"""

import subprocess

from watchfiles import PythonFilter, watch

BOT_COMMAND = ("uv", "run", "--no-sync", "bot")
WATCH_PATH = "./src"


def dev() -> None:
    process = subprocess.Popen(BOT_COMMAND)
    try:
        for _changes in watch(WATCH_PATH, watch_filter=PythonFilter()):
            print("src changed, restarting bot...", flush=True)
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            process = subprocess.Popen(BOT_COMMAND)
    except KeyboardInterrupt:
        pass
    finally:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


if __name__ == "__main__":
    dev()
