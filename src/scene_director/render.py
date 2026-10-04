"""Render a ShotList to JSON and Markdown."""

from __future__ import annotations

import json

from .director import ShotList


def to_json(shot_list: ShotList, indent: int = 2) -> str:
    return json.dumps(shot_list.to_dict(), indent=indent, ensure_ascii=False)


def _fmt_time(seconds: float) -> str:
    m, s = divmod(seconds, 60)
    return f"{int(m)}:{s:04.1f}"


def to_markdown(shot_list: ShotList, prompts: bool = True) -> str:
    sl = shot_list
    out = [
        f"# {sl.title} \u2014 Shot List",
        "",
        f"**Style:** `{sl.style}` \u00b7 **Aspect:** `{sl.aspect}` \u00b7 **Scenes:** {len(sl.scenes)} \u00b7 "
        f"**Shots:** {len(sl.shots)} \u00b7 **Runtime:** ~{sl.duration:g}s",
    ]
    extra = {k: v for k, v in sl.meta.items() if k != "title"}
    if extra:
        out += ["", " \u00b7 ".join(f"**{k.title()}:** {v}" for k, v in extra.items())]

    clock = 0.0
    for sc in sl.scenes:
        out += ["", f"## Scene {sc.number}: {sc.heading}", "", f"_{sc.summary}._ Lighting: {sc.lighting}. ~{sc.duration:g}s", ""]
        out += ["| Shot | Time | Type | Camera | Dur | Description |", "|---|---|---|---|---|---|"]
        for sh in sc.shots:
            desc = sh.description.replace("|", "\\|")
            out.append(f"| `{sh.id}` | {_fmt_time(clock)} | {sh.shot_type} | {sh.camera_move} | {sh.duration:g}s | {desc} |")
            clock += sh.duration
        if prompts:
            out.append("")
            for sh in sc.shots:
                out += [
                    "<details>",
                    f"<summary><b>{sh.id}</b> prompts</summary>",
                    "",
                    "**Image (Flux / SDXL / DALL\u00b7E)**",
                    "```text",
                    sh.image_prompt,
                    "```",
                    "**Midjourney**",
                    "```text",
                    sh.midjourney_prompt,
                    "```",
                    "**Video (Runway / Kling / Veo / Sora)**",
                    "```text",
                    sh.video_prompt,
                    "```",
                    f"**Negative:** {sh.negative_prompt}",
                    "",
                    "</details>",
                ]
    out.append("")
    return "\n".join(out)
