"""scene-director CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .director import ASPECTS, STYLES, direct
from .parser import parse_script
from .render import to_json, to_markdown


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="scene-director", description="Turn a screenplay into an AI video shot list.")
    p.add_argument("script", help="path to a .fountain / .txt screenplay, or '-' for stdin")
    p.add_argument("-s", "--style", default="cinematic", choices=sorted(STYLES))
    p.add_argument("-a", "--aspect", default="16:9", choices=sorted(ASPECTS))
    p.add_argument("-c", "--cast", help="JSON file mapping character names to visual descriptions")
    p.add_argument("-o", "--out", help="output directory (writes <name>.shots.json and <name>.shots.md)")
    p.add_argument("-f", "--format", choices=["md", "json", "summary"], default="summary", help="stdout format when --out is not given")
    p.add_argument("--no-prompts", action="store_true", help="omit prompts from the Markdown output")
    p.add_argument("--version", action="version", version=f"scene-director {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    text = sys.stdin.read() if args.script == "-" else Path(args.script).read_text(encoding="utf-8")
    cast = json.loads(Path(args.cast).read_text(encoding="utf-8")) if args.cast else None

    script = parse_script(text)
    if not script.scenes:
        print("error: no scene headings found (expected lines like 'INT. CAFE - DAY')", file=sys.stderr)
        return 1
    shots = direct(script, style=args.style, aspect=args.aspect, cast=cast)

    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        stem = Path(args.script).stem if args.script != "-" else "script"
        (out / f"{stem}.shots.json").write_text(to_json(shots) + "\n", encoding="utf-8")
        (out / f"{stem}.shots.md").write_text(to_markdown(shots, prompts=not args.no_prompts), encoding="utf-8")
        print(f"\u2714 {len(shots.scenes)} scenes, {len(shots.shots)} shots, ~{shots.duration:g}s \u2192 {out}/{stem}.shots.{{json,md}}")
        return 0

    if args.format == "json":
        print(to_json(shots))
    elif args.format == "md":
        print(to_markdown(shots, prompts=not args.no_prompts))
    else:
        print(f"{shots.title}  \u00b7  style={shots.style}  aspect={shots.aspect}  ~{shots.duration:g}s\n")
        for sc in shots.scenes:
            print(f"Scene {sc.number}  {sc.heading}  (~{sc.duration:g}s)")
            for sh in sc.shots:
                print(f"  {sh.id}  {sh.shot_type:<26} {sh.camera_move:<26} {sh.duration:>4g}s")
            print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
