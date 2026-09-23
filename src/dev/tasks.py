"""Команды разработчика.

Каждая функция зарегистрирована как консольный скрипт
и запускается напрямую: `uv run <command>`.
"""

import subprocess
import sys

PYTHON = sys.executable


def _run(*command: str) -> None:
    raise SystemExit(subprocess.call(command))


def _run_sequence(*commands: tuple[str, ...]) -> None:
    for command in commands:
        code = subprocess.call(command)
        if code != 0:
            raise SystemExit(code)


def test() -> None:
    _run(PYTHON, "-m", "pytest", "-v")


def lint() -> None:
    _run(PYTHON, "-m", "ruff", "check", ".")


def fmt() -> None:
    _run(PYTHON, "-m", "ruff", "format", ".")


def fmt_check() -> None:
    _run(PYTHON, "-m", "ruff", "format", "--check", ".")


def typecheck() -> None:
    _run(PYTHON, "-m", "mypy", ".")


def check() -> None:
    _run_sequence(
        (PYTHON, "-m", "ruff", "check", "."),
        (PYTHON, "-m", "ruff", "format", "--check", "."),
        (PYTHON, "-m", "pytest", "-q"),
    )


def precommit() -> None:
    _run(PYTHON, "-m", "pre_commit", "run", "--all-files")


def install_hooks() -> None:
    _run(PYTHON, "-m", "pre_commit", "install")


def migrate() -> None:
    _run(PYTHON, "-m", "alembic", "upgrade", "head")
