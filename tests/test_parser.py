from pathlib import Path

from scene_director import parse_script

SAMPLE = Path(__file__).resolve().parents[1] / "examples" / "northbank-cold-brew.fountain"


def test_parses_title_page_and_scenes():
    script = parse_script(SAMPLE.read_text())
    assert script.title.startswith("Northbank Cold Brew")
    assert script.meta["brand"].startswith("Northbank")
    assert [s.time for s in script.scenes] == ["DAWN", "MORNING", "DAY", "DUSK"]
    assert script.scenes[1].location == "Maya's Flat - Kitchen"
    assert script.scenes[0].interior is False and script.scenes[1].interior is True


def test_dialogue_extensions_and_parentheticals():
    script = parse_script(SAMPLE.read_text())
    vo = script.scenes[0].beats[1]
    assert vo.kind == "dialogue" and vo.character == "Maya" and vo.extension == "V.O."
    line = next(b for b in script.scenes[1].beats if b.kind == "dialogue")
    assert line.parenthetical == "to camera, half asleep"
    assert line.text == "Okay. Let's actually do this."
    assert script.scenes[2].characters == ["Dev", "Maya"]  # order of first line


def test_ignores_notes_comments_and_transitions():
    text = """
INT. STUDIO - NIGHT
[[note to self: add rain]]
// a comment
A neon sign flickers.

CUT TO:

EXT. STREET - NIGHT

Rain hammers the pavement.
"""
    script = parse_script(text)
    assert len(script.scenes) == 2
    assert script.scenes[0].beats[0].text == "A neon sign flickers."
    assert all("CUT TO" not in b.text for s in script.scenes for b in s.beats)
    assert script.title == "Untitled"


def test_heading_without_time_defaults_to_day():
    script = parse_script("EXT. PARK\n\nKids play football.")
    assert script.scenes[0].time == "DAY"
    assert script.scenes[0].location == "Park"
