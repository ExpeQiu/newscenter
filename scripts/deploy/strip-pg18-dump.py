#!/usr/bin/env python3
"""去掉 PG18 dump 中云端 PG16 不认识的 \\restrict / \\unrestrict。"""
from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 3:
        print(f"用法: {sys.argv[0]} <in.sql> <out.sql>", file=sys.stderr)
        return 2
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    lines = src.read_text(encoding="utf-8", errors="replace").splitlines(True)
    skip_prefixes = ("\\restrict", "\\unrestrict")
    out: list[str] = []
    for ln in lines:
        if ln.startswith(skip_prefixes):
            continue
        if "transaction_timeout" in ln:
            continue
        out.append(ln)
    dst.write_text("".join(out), encoding="utf-8")
    print(f"stripped {len(lines) - len(out)} lines → {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
