#!/usr/bin/env python3
"""bump_version.py — поднять версию ATLAS и закрыть раздел CHANGELOG.

    python3 scripts/bump_version.py patch   # 0.9.0 → 0.9.1  мелкие правки
    python3 scripts/bump_version.py minor   # 0.9.1 → 0.10.0 заметные изменения
    python3 scripts/bump_version.py major   # 0.10.0 → 1.0.0 несовместимые

Что делает:
  1. src/atlas/__init__.py: __version__ = новая версия (единственный источник).
  2. CHANGELOG.md: «## [Unreleased]» → «## [X.Y.Z] — YYYY-MM-DD», сверху
     заводится пустой [Unreleased]. Пустой Unreleased — ошибка: версия без
     описания изменений не нужна.

Коммит и тег — вручную (скрипт печатает команды). Правила выбора patch/minor —
CLAUDE.md, раздел «Версионирование».
"""
from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INIT = ROOT / "src" / "atlas" / "__init__.py"
CHANGELOG = ROOT / "CHANGELOG.md"
VERSION_RE = re.compile(r'^__version__ = "(\d+)\.(\d+)\.(\d+)"$', re.M)
UNRELEASED = "## [Unreleased]"


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in ("patch", "minor", "major"):
        print(__doc__)
        return 2
    part = argv[1]

    init_text = INIT.read_text(encoding="utf-8")
    m = VERSION_RE.search(init_text)
    if not m:
        print(f"__version__ не найден в {INIT}", file=sys.stderr)
        return 1
    major, minor, patch = map(int, m.groups())
    if part == "major":
        major, minor, patch = major + 1, 0, 0
    elif part == "minor":
        minor, patch = minor + 1, 0
    else:
        patch += 1
    old, new = ".".join(m.groups()), f"{major}.{minor}.{patch}"

    log = CHANGELOG.read_text(encoding="utf-8")
    if UNRELEASED not in log:
        print(f"В CHANGELOG.md нет раздела {UNRELEASED}", file=sys.stderr)
        return 1
    start = log.index(UNRELEASED) + len(UNRELEASED)
    end = log.find("\n## [", start)
    body = log[start:end if end != -1 else len(log)]
    if not re.search(r"^- ", body, re.M):
        print("Раздел [Unreleased] пуст — сначала опишите изменения.", file=sys.stderr)
        return 1

    INIT.write_text(VERSION_RE.sub(f'__version__ = "{new}"', init_text, count=1), encoding="utf-8")
    CHANGELOG.write_text(
        log.replace(UNRELEASED, f"{UNRELEASED}\n\n---\n\n## [{new}] — {date.today().isoformat()}", 1),
        encoding="utf-8",
    )
    print(f"{old} → {new}")
    print("Дальше:")
    print(f'  git commit -am "chore(release): v{new}"')
    print(f"  git tag -a v{new} -m v{new} && git push origin main v{new}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
