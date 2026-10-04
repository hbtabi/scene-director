"""Heuristic 'director' that turns parsed scenes into a shot list with model prompts."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from importlib import resources
from string import Template

from .parser import Beat, Scene, Script

# --------------------------------------------------------------------- styles
STYLES: dict[str, dict[str, str]] = {
    "cinematic": {
        "look": "Cinematic film still, anamorphic, shallow depth of field, subtle film grain",
        "motion": "Smooth cinematic motion, natural motion blur, 24fps feel",
        "palette": "teal and warm amber",
        "lens": "35mm anamorphic",
        "negative": "blurry, extra fingers, distorted faces, text, watermark, low quality, cartoon",
    },
    "ugc": {
        "look": "Authentic UGC-style smartphone footage, natural skin texture, unpolished, relatable",
        "motion": "Handheld phone camera, slight shake, vertical framing, creator talking to camera",
        "palette": "natural, true-to-life colours",
        "lens": "smartphone front camera, 26mm equivalent",
        "negative": "studio lighting, overly polished, CGI look, text, watermark, extra fingers",
    },
    "commercial": {
        "look": "Premium commercial photography, crisp, high contrast, glossy product highlights",
        "motion": "Controlled gimbal moves, slow-motion product moments, clean transitions",
        "palette": "brand-led, bold and saturated",
        "lens": "50mm macro and 24mm wide",
        "negative": "noise, clutter, distorted product, warped labels, text, watermark",
    },
    "anime": {
        "look": "Hand-painted anime key visual, clean line art, painterly backgrounds",
        "motion": "Limited-animation style, expressive poses, parallax backgrounds",
        "palette": "soft pastel with vivid accents",
        "lens": "virtual 35mm",
        "negative": "photorealistic, 3d render, deformed hands, text, watermark",
    },
}

LIGHTING = {
    "DAY": "soft natural daylight",
    "MORNING": "fresh morning light, long soft shadows",
    "AFTERNOON": "bright afternoon sun",
    "DAWN": "pale blue dawn light",
    "DUSK": "golden-hour backlight",
    "EVENING": "warm practical lamps, early evening",
    "NIGHT": "moody night lighting with neon and practical sources",
    "CONTINUOUS": "lighting matching the previous shot",
}

ASPECTS = {"16:9", "9:16", "1:1", "4:5", "2.39:1"}

# keyword -> (shot type, camera move)
_CLOSE = re.compile(r"\b(eyes?|face|smiles?|tears?|lips|whispers?|stares?|glances?|expression|reacts?)\b", re.I)
_INSERT = re.compile(r"\b(hands?|fingers?|phone|screen|cup|can|bottle|logo|label|product|watch|keys?|pours?|sips?|taps?)\b", re.I)
_MOVE = re.compile(r"\b(walks?|runs?|rushes|enters?|exits?|crosses|drives?|cycles?|dances?|steps?)\b", re.I)
_REVEAL = re.compile(r"\b(reveals?|appears?|unveils?|opens?|bursts?)\b", re.I)
_WIDE = re.compile(r"\b(skyline|street|crowd|city|rooftop|room fills|everyone|panorama)\b", re.I)
_EMOTION = re.compile(r"\b(quietly|whisper|softly|tearful|beat|emotional|nervous|stunned)\b", re.I)


@dataclass
class Shot:
    id: str
    scene: int
    shot_type: str
    camera_move: str
    duration: float
    description: str
    characters: list[str] = field(default_factory=list)
    dialogue: str | None = None
    speaker: str | None = None
    image_prompt: str = ""
    midjourney_prompt: str = ""
    video_prompt: str = ""
    negative_prompt: str = ""


@dataclass
class SceneBlock:
    number: int
    heading: str
    location: str
    time: str
    lighting: str
    summary: str
    shots: list[Shot]

    @property
    def duration(self) -> float:
        return round(sum(s.duration for s in self.shots), 1)


@dataclass
class ShotList:
    title: str
    style: str
    aspect: str
    meta: dict[str, str]
    scenes: list[SceneBlock]

    @property
    def shots(self) -> list[Shot]:
        return [s for sc in self.scenes for s in sc.shots]

    @property
    def duration(self) -> float:
        return round(sum(sc.duration for sc in self.scenes), 1)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["total_duration"] = self.duration
        d["shot_count"] = len(self.shots)
        for sc, raw in zip(self.scenes, d["scenes"]):
            raw["duration"] = sc.duration
        return d


# ------------------------------------------------------------------- helpers
def _template(name: str) -> Template:
    return Template(resources.files("scene_director").joinpath(f"templates/{name}.txt").read_text(encoding="utf-8").strip())


def _round_half(x: float) -> float:
    return round(x * 2) / 2


def dialogue_duration(text: str) -> float:
    """~2.6 spoken words per second, plus a breath. Clamped to 2-8 s."""
    words = len(text.split())
    return max(2.0, min(8.0, _round_half(words / 2.6 + 0.8)))


def action_duration(text: str) -> float:
    words = len(text.split())
    return max(2.0, min(6.0, _round_half(2.0 + words / 12)))


def _first_sentence(text: str) -> str:
    return re.split(r"(?<=[.!?])\s+", text.strip())[0].rstrip(".")


_LOWERABLE = {"a", "an", "the", "she", "he", "they", "her", "his", "their", "it", "its", "we", "our", "mist", "rain", "snow", "smoke", "light", "sunlight", "silence", "music"}


def _lower_first(s: str) -> str:
    """Lower-case the first word only when it is clearly not a proper noun."""
    first = s.split(" ", 1)[0] if s else ""
    return s[:1].lower() + s[1:] if first.lower() in _LOWERABLE else s


_GENERIC_PLACES = {
    "rooftop", "kitchen", "flat", "apartment", "office", "street", "cafe", "café", "car", "studio", "bedroom", "park",
    "gym", "shop", "bar", "warehouse", "space", "co-working", "alley", "beach", "station", "restaurant", "living", "room",
    "bathroom", "hallway", "lobby", "classroom", "garden", "market", "corridor", "lift", "stairwell", "barbershop", "salon",
}


def _place_name(location: str) -> str:
    base = location.split(" - ")[0].strip()
    words = [w.lower() for w in base.split()]
    if words and all(w in _GENERIC_PLACES for w in words):
        return f"the {base.lower()}"
    return base


def classify_action(text: str, is_first: bool) -> tuple[str, str]:
    if is_first or _WIDE.search(text):
        return ("Wide establishing shot", "slow push-in") if is_first else ("Wide shot", "slow pan")
    if _REVEAL.search(text):
        return "Medium shot", "push-in reveal"
    if _INSERT.search(text):
        return "Insert close-up", "static, macro focus pull"
    if _CLOSE.search(text):
        return "Close-up", "subtle push-in"
    if _MOVE.search(text):
        return "Medium tracking shot", "tracking alongside subject"
    return "Medium shot", "static"


def classify_dialogue(beat: Beat, prev_speaker: str | None, speakers: list[str]) -> tuple[str, str]:
    if beat.extension in {"V.O.", "VO"}:
        return "Cutaway B-roll", "slow drift"
    if beat.parenthetical and _EMOTION.search(beat.parenthetical):
        return "Close-up", "slow push-in"
    if prev_speaker and prev_speaker != beat.character and len(speakers) >= 2:
        return "Over-the-shoulder shot", "static"
    return "Medium close-up", "static"


_PRONOUN = re.compile(r"^(she|he|they|her|his|their)\b", re.I)


def _subject_for(text: str, characters: list[str], last: str | None = None, fallback: str = "the scene") -> str:
    """Who/what the shot is about: named characters, else the last-mentioned one for a pronoun, else the place."""
    named = [c for c in characters if re.search(rf"\b{re.escape(c)}\b", text, re.I)]
    if named:
        return " and ".join(named)
    if last and _PRONOUN.search(text.strip()):
        return last
    return fallback


# -------------------------------------------------------------------- direct
def direct(script: Script, style: str = "cinematic", aspect: str = "16:9", cast: dict[str, str] | None = None) -> ShotList:
    """Build a ShotList from a parsed Script.

    cast: optional {"Maya": "late-20s British-Pakistani woman, curly hair, green bomber jacket"}
          used to keep characters visually consistent across prompts.
    """
    if style not in STYLES:
        raise ValueError(f"Unknown style '{style}'. Choose from: {', '.join(STYLES)}")
    if aspect not in ASPECTS:
        raise ValueError(f"Unsupported aspect '{aspect}'. Choose from: {', '.join(sorted(ASPECTS))}")
    look = STYLES[style]
    cast = {k.title(): v for k, v in (cast or {}).items()}
    tpl_img, tpl_mj, tpl_vid = _template("image"), _template("midjourney"), _template("video")
    neg_short = ", ".join(look["negative"].split(", ")[:4])

    blocks: list[SceneBlock] = []
    for scene in script.scenes:
        lighting = LIGHTING.get(scene.time.split()[0], LIGHTING["DAY"])
        setting = f"{'Interior' if scene.interior else 'Exterior'}, {scene.location}"
        place = _place_name(scene.location)
        last_person: str | None = None
        speakers = scene.characters
        everyone = _all_people(script)
        planned: list[tuple[Shot, str, str, str]] = []  # (shot, subject, video action, still-image action)
        prev_speaker: str | None = None
        first_action = next((b.text for b in scene.beats if b.kind == "action"), scene.location)

        for beat in scene.beats:
            if beat.kind == "action":
                shot_type, move = classify_action(beat.text, is_first=not planned)
                subject = _subject_for(beat.text, everyone, last_person, place)
                action = _lower_first(_first_sentence(beat.text))
                chars = [c for c in everyone if re.search(rf"\b{re.escape(c)}\b", beat.text, re.I)]
                if not chars and subject in everyone:
                    chars = [subject]
                if chars:
                    last_person = chars[-1]
                shot = Shot("", scene.number, shot_type, move, action_duration(beat.text), beat.text, characters=chars)
                planned.append((shot, subject, action, action))
                continue

            if not planned:  # dialogue opens the scene: establish the space first
                est = _establishing(scene, first_action)
                est_action = _lower_first(_first_sentence(first_action))
                planned.append((est, place, est_action, est_action))
            shot_type, move = classify_dialogue(beat, prev_speaker, speakers)
            speaker = beat.character or "the speaker"
            subject = speaker
            if shot_type.startswith("Over-the-shoulder") and prev_speaker:
                subject = f"{speaker}, seen over {prev_speaker}'s shoulder"
            tone = f" ({beat.parenthetical})" if beat.parenthetical else ""
            video_action = f"speaking{tone}: \u201c{beat.text}\u201d"
            still_action = f"mid-sentence ({beat.parenthetical})" if beat.parenthetical else "mid-sentence, natural expression"
            if beat.extension in {"V.O.", "VO"}:
                subject = place
                video_action = still_action = f"atmospheric b-roll evoking the voice-over line \u201c{beat.text}\u201d"
            shot = Shot("", scene.number, shot_type, move, dialogue_duration(beat.text), f"{speaker}{tone}: \u201c{beat.text}\u201d",
                        characters=[speaker] if beat.character else [], dialogue=beat.text, speaker=beat.character)
            planned.append((shot, subject, video_action, still_action))
            prev_speaker = beat.character
            last_person = beat.character or last_person

        shots: list[Shot] = []
        for n, (shot, subject, video_action, still_action) in enumerate(planned, 1):
            shot.id = f"S{scene.number:02d}-{n:02d}"
            notes = "; ".join(f"{c}: {cast[c]}" for c in shot.characters if c in cast)
            if still_action.lower().startswith(subject.lower()):
                # "Maya walks through..." already names the subject, so don't repeat it.
                lead, lead_video = f"{shot.shot_type}: {still_action}", f"{shot.shot_type}: {video_action}"
            else:
                lead = f"{shot.shot_type} of {subject}, {still_action}"
                lead_video = f"{shot.shot_type} of {subject}: {video_action}"
            values = {
                "lead": lead,
                "lead_video": lead_video,
                "shot_type": shot.shot_type,
                "subject": subject,
                "action": still_action,
                "setting": setting,
                "lighting": lighting,
                "style_look": look["look"],
                "style_motion": look["motion"],
                "palette": look["palette"],
                "lens": look["lens"],
                "composition": _composition(shot.shot_type, aspect),
                "aspect": aspect,
                "duration": f"{shot.duration:g}",
                "camera_move": shot.camera_move.capitalize(),
                "negative_short": neg_short,
                "character_notes": f" ({notes})" if notes else "",
                "dialogue_note": f"{shot.speaker} lip-syncs the line naturally." if shot.dialogue and "B-roll" not in shot.shot_type else "",
            }
            shot.image_prompt = _clean(tpl_img.safe_substitute(values))
            shot.midjourney_prompt = _clean(tpl_mj.safe_substitute(values))
            shot.video_prompt = _clean(tpl_vid.safe_substitute(values))
            shot.negative_prompt = look["negative"]
            shots.append(shot)

        blocks.append(SceneBlock(scene.number, scene.heading, scene.location, scene.time, lighting,
                                 _first_sentence(first_action), shots))

    return ShotList(script.title, style, aspect, script.meta, blocks)


def _establishing(scene: Scene, first_action: str) -> Shot:
    return Shot("", scene.number, "Wide establishing shot", "slow push-in", 2.5, f"Establish {scene.location}. {first_action}")


def _all_people(script: Script) -> list[str]:
    seen: list[str] = []
    for sc in script.scenes:
        for c in sc.characters:
            if c not in seen:
                seen.append(c)
    return seen


def _composition(shot_type: str, aspect: str) -> str:
    vertical = aspect in {"9:16", "4:5"}
    if shot_type.startswith("Wide"):
        return "subject small in frame, strong leading lines" + (", stacked vertically" if vertical else ", rule of thirds")
    if "Insert" in shot_type:
        return "tight macro framing, object fills the frame, clean background"
    if "Over-the-shoulder" in shot_type:
        return "foreground shoulder out of focus, speaker on the opposite third"
    if "Close" in shot_type:
        return "face fills upper two-thirds, eyes on the top third line"
    return "waist-up framing, centred" if vertical else "waist-up framing, subject on a third"


def _clean(s: str) -> str:
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s+([,.])", r"\1", s)
    s = re.sub(r"\s*[,:]\s*\.", ".", s)
    s = re.sub(r",\s*,", ",", s)
    s = s.replace(".,", ",").replace("..", ".").replace(".\u201d.", ".\u201d")
    return s.strip()
