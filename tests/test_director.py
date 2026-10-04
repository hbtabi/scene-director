import json
from pathlib import Path

import pytest

from scene_director import STYLES, direct, parse_script, to_json, to_markdown
from scene_director.cli import main
from scene_director.director import action_duration, classify_action, dialogue_duration

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "examples" / "northbank-cold-brew.fountain"
CAST = json.loads((ROOT / "examples" / "cast.json").read_text())


@pytest.fixture
def shots():
    return direct(parse_script(SAMPLE.read_text()), style="cinematic", aspect="9:16", cast=CAST)


def test_durations_are_sane():
    assert dialogue_duration("Hi.") == 2.0
    assert dialogue_duration(" ".join(["word"] * 100)) == 8.0
    assert 2.0 <= action_duration("She walks in.") <= 6.0
    assert (dialogue_duration("one two three four five six seven eight") * 2) % 1 == 0  # half-second grid


def test_shot_classification():
    assert classify_action("The skyline glows.", is_first=True)[0] == "Wide establishing shot"
    assert classify_action("Her hand grips the phone.", is_first=False)[0] == "Insert close-up"
    assert classify_action("He stares at the door.", is_first=False)[0] == "Close-up"
    assert classify_action("Maya walks to the bus.", is_first=False)[0] == "Medium tracking shot"


def test_shot_list_structure(shots):
    assert len(shots.scenes) == 4
    ids = [s.id for s in shots.shots]
    assert ids[0] == "S01-01" and len(ids) == len(set(ids))
    assert all(s.image_prompt and s.video_prompt and s.midjourney_prompt for s in shots.shots)
    assert all("--ar 9:16" in s.midjourney_prompt for s in shots.shots)
    assert shots.duration == pytest.approx(sum(s.duration for s in shots.shots))


def test_dialogue_shots_and_ots(shots):
    scene3 = shots.scenes[2]
    types = [s.shot_type for s in scene3.shots]
    assert "Over-the-shoulder shot" in types
    ots = scene3.shots[types.index("Over-the-shoulder shot")]
    assert ots.speaker == "Maya" and "Dev's shoulder" in ots.image_prompt
    assert "lip-syncs" in ots.video_prompt


def test_cast_descriptions_injected(shots):
    maya_shots = [s for s in shots.shots if "Maya" in s.characters]
    assert maya_shots and all("sage-green hoodie" in s.image_prompt for s in maya_shots)


def test_prompts_have_no_template_leftovers(shots):
    for s in shots.shots:
        for p in (s.image_prompt, s.video_prompt, s.midjourney_prompt):
            assert "$" not in p and ".," not in p and "  " not in p


@pytest.mark.parametrize("style", sorted(STYLES))
def test_every_style_renders(style):
    sl = direct(parse_script(SAMPLE.read_text()), style=style)
    assert STYLES[style]["look"] in sl.shots[0].image_prompt


def test_invalid_options():
    script = parse_script(SAMPLE.read_text())
    with pytest.raises(ValueError):
        direct(script, style="vaporwave")
    with pytest.raises(ValueError):
        direct(script, aspect="3:2")


def test_renderers(shots):
    data = json.loads(to_json(shots))
    assert data["shot_count"] == len(shots.shots) and data["total_duration"] == shots.duration
    md = to_markdown(shots)
    assert md.startswith("# Northbank Cold Brew")
    assert "| `S01-01` | 0:00.0 |" in md
    assert "<details>" not in to_markdown(shots, prompts=False)


def test_cli_writes_outputs(tmp_path, capsys):
    assert main([str(SAMPLE), "-a", "9:16", "-c", str(ROOT / "examples" / "cast.json"), "-o", str(tmp_path)]) == 0
    assert (tmp_path / "northbank-cold-brew.shots.json").exists()
    assert (tmp_path / "northbank-cold-brew.shots.md").exists()
    assert "13 shots" in capsys.readouterr().out


def test_sample_output_is_up_to_date(tmp_path):
    """The committed example output must match what the code generates today."""
    main([str(SAMPLE), "-a", "9:16", "-c", str(ROOT / "examples" / "cast.json"), "-o", str(tmp_path)])
    for name in ("northbank-cold-brew.shots.json", "northbank-cold-brew.shots.md"):
        assert (tmp_path / name).read_text() == (ROOT / "examples" / "output" / name).read_text()
