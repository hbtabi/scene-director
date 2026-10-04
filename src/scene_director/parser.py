"""A small, forgiving screenplay parser (Fountain-flavoured).

Understands:
  * scene headings:   INT. CAFE - DAY  /  EXT. ROOFTOP - NIGHT  /  INT./EXT. CAR - DUSK
  * character cues:   MAYA  or  MAYA (V.O.)  followed by dialogue lines
  * parentheticals:   (whispering)
  * action:           any other paragraph
  * title page keys:  Title: ... / Brand: ... before the first heading
  * notes:            [[ ... ]] are ignored, as are lines starting with //
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

HEADING = re.compile(
    r"^(?P<prefix>INT\./EXT\.|EXT\./INT\.|I/E\.?|INT\.?|EXT\.?)\s+(?P<location>.+?)(?:\s+[-–—]\s+(?P<time>[A-Z][A-Z ]*))?$"
)
CHARACTER = re.compile(r"^(?P<name>[A-Z][A-Z0-9 .'\-]{1,30}?)(?:\s*\((?P<ext>[A-Z.\s']+)\))?\s*\^?$")
TITLE_KEY = re.compile(r"^(?P<key>[A-Za-z][A-Za-z ]{0,20}):\s*(?P<value>.+)$")
TRANSITION = re.compile(r"^(?:[A-Z ]+ TO:|FADE (?:IN|OUT)\.?:?|CUT TO BLACK\.?)$")


@dataclass
class Beat:
    kind: Literal["action", "dialogue"]
    text: str
    character: str | None = None
    parenthetical: str | None = None
    extension: str | None = None  # V.O., O.S., ...


@dataclass
class Scene:
    number: int
    heading: str
    interior: bool
    location: str
    time: str
    beats: list[Beat] = field(default_factory=list)

    @property
    def characters(self) -> list[str]:
        seen: list[str] = []
        for b in self.beats:
            if b.character and b.character not in seen:
                seen.append(b.character)
        return seen


@dataclass
class Script:
    title: str
    meta: dict[str, str]
    scenes: list[Scene]


def _titlecase(text: str) -> str:
    """'MAYA'S FLAT - KITCHEN' -> "Maya's Flat - Kitchen" (str.title() would give "Maya'S")."""
    return " ".join(w.capitalize() for w in text.split(" "))


def _paragraphs(text: str) -> list[list[str]]:
    text = re.sub(r"\[\[.*?\]\]", "", text, flags=re.S)
    paras, cur = [], []
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.strip().startswith("//"):
            continue
        if not line.strip():
            if cur:
                paras.append(cur)
                cur = []
            continue
        cur.append(line.strip())
    if cur:
        paras.append(cur)
    return paras


def parse_script(text: str) -> Script:
    meta: dict[str, str] = {}
    scenes: list[Scene] = []

    for para in _paragraphs(text):
        first = para[0]

        heading = HEADING.match(first.upper()) if first.upper() == first else None
        if heading and first.startswith(("INT", "EXT", "I/E")):
            prefix = heading.group("prefix")
            scene = Scene(
                number=len(scenes) + 1,
                heading=first,
                interior=prefix.startswith(("INT", "I/E")),
                location=_titlecase(heading.group("location").strip()),
                time=(heading.group("time") or "DAY").strip(),
            )
            scenes.append(scene)
            # Allow action directly under the heading without a blank line.
            if len(para) > 1:
                scene.beats.append(Beat("action", " ".join(para[1:])))
            continue

        if not scenes:
            for line in para:
                m = TITLE_KEY.match(line)
                if m:
                    meta[m.group("key").strip().lower()] = m.group("value").strip()
            continue

        scene = scenes[-1]
        if TRANSITION.match(first):
            continue

        cue = CHARACTER.match(first)
        if cue and len(para) > 1 and first == first.upper():
            parenthetical = None
            lines = para[1:]
            if lines and lines[0].startswith("(") and lines[0].endswith(")"):
                parenthetical = lines[0][1:-1].strip()
                lines = lines[1:]
            scene.beats.append(
                Beat(
                    "dialogue",
                    " ".join(lines).strip(),
                    character=_titlecase(cue.group("name").strip()),
                    parenthetical=parenthetical,
                    extension=(cue.group("ext") or "").replace(" ", "") or None,
                )
            )
            continue

        scene.beats.append(Beat("action", " ".join(para)))

    return Script(title=meta.get("title", "Untitled"), meta=meta, scenes=scenes)
