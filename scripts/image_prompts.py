"""Story-aware image prompt planning for the CH-666 illustrations.

The old prompts were one fixed template per channel plus the story title, so every
cover and scene looked alike and had little to do with the actual story. This module
builds each prompt from two things:

* the story itself (summary, director analysis and three story beats), turned into a
  concrete English scene description by a text model (``ask`` callback), and
* a seeded visual "recipe" (shot type, light, colour palette, film look and details)
  that stays reproducible for one story while differing between its images.

No network access happens here. If the text model is unavailable or returns something
unusable, a rule-based fallback still produces a varied, story-flavoured prompt.
"""
from __future__ import annotations

import random
import re
from html.parser import HTMLParser
from typing import Callable, Optional

# Kinds map to uploaded file names: <story_code>_<kind>.webp.
# "cover" and "scene" are the two images the website already uses.
BASE_KINDS = ("cover", "scene")
EXTENDED_KINDS = ("cover", "scene_open", "scene", "scene_end")

PALETTES = {
    "3": [
        "deep vermilion and soot black with faint gold dust",
        "moonlit indigo and aged jade green, cold breath mist",
        "candle amber and bone white, cedar-wood shadows",
        "funeral white and ink black with a single red thread",
        "rain-soaked temple greys with sodium-orange lantern glow",
        "dusty sepia and cold cyan, like an old photograph",
        "mineral green and oxidised copper with warm paper white",
        "smoky plum, tarnished brass and charcoal",
        "pale rice-paper cream with indigo ink and one vermilion accent",
        "blue-black night with scattered warm window light",
        "weathered jade, dark umber and muted persimmon",
    ],
    "6": [
        "sodium-vapor orange against cold blue shadow",
        "sickly fluorescent green-white and concrete grey",
        "neon-pink reflections on wet asphalt, deep navy",
        "dim tungsten yellow and mould green interiors",
        "washed-out overcast grey-blue, desaturated and flat",
        "security-camera green monochrome with magenta noise",
        "bleached fluorescent white and dusty lavender-grey",
        "petrol blue with sodium-yellow highlights",
        "faded cyan and brown, like a sun-damaged print",
        "deep burgundy and dirty fluorescent mint",
        "near-monochrome charcoal with one electric-blue detail",
    ],
    "9": [
        "deep indigo with restrained warning red",
        "bleached white void with one black geometric intrusion",
        "ultraviolet violet and chrome, impossible geometry",
        "rust orange dust and ash grey, vast empty scale",
        "clinical cyan-white light, sterile and cold",
        "inverted negative tones, deep teal and bone",
        "oxidised copper, blackened silver and cold white",
        "ultraviolet and bruised rose with deep shadow",
        "dusty ochre against an immense blue-black void",
        "pale stone, faded crimson and graphite",
        "iridescent oil-slick colour against absolute black",
    ],
}

LOOKS = {
    "3": [
        "35mm film still, fine grain",
        "ink-wash painting with muted colour accents",
        "oil painting with visible brush strokes, Taiwanese gothic mood",
        "documentary photograph, handheld, available light",
        "16mm film frame, halation and soft focus",
    ],
    "6": [
        "35mm film still, fine grain",
        "low-resolution CCTV frame, compression artifacts",
        "disposable-camera flash photograph, harsh direct flash",
        "VHS home-video freeze frame, tracking noise",
        "documentary photograph, handheld, available light",
        "moody digital cinema still, anamorphic lens",
    ],
    "9": [
        "moody digital cinema still, anamorphic lens",
        "medium-format photograph, shallow depth of field",
        "matte-painting style concept art, vast scale",
        "35mm film still, fine grain",
        "surreal conceptual photograph, hard studio light",
    ],
}

# The four visual dice are drawn independently with a per-story RNG, then dealt
# without replacement across that story's images.  Style descriptions are kept
# internally coherent (for example, VHS only appears with analog treatments).
GENRES = {
    "3": ["cinematic horror still, restrained 35mm grain", "documentary photography, available light", "Taiwanese ink print with muted pigments", "folk-horror oil painting, visible brushwork", "hand-painted concept art, tactile paper texture", "archival 16mm film frame, soft halation", "woodblock print with coarse registration", "miniature theatre set photographed on film", "charcoal and watercolour on rough paper", "antique etching with selective colour", "soft pastel painting with unsettling shadows", "monochrome silver-gelatin photograph"],
    "6": ["cinematic horror still, anamorphic framing", "documentary photography, handheld available light", "CCTV surveillance frame, compressed monochrome", "VHS home-video freeze frame, tracking noise", "linocut print with rough carved shadows", "moody digital concept art, realistic surfaces", "risograph print with misregistered colours", "flash-lit disposable-camera photograph", "architectural blueprint illustration turned uncanny", "newsprint halftone illustration", "miniature diorama with practical lighting", "infrared night-vision photograph", "graphic novel panel with restrained inkwork", "long-exposure urban photography"],
    "9": ["cinematic science-fiction horror still", "medium-format photography, deep spatial detail", "surreal conceptual photography, hard studio light", "matte-painted concept art, vast scale", "archival analog film frame, faded colour", "graphic screenprint with stark shapes", "photogrammetry-inspired 3D render", "collage of archival photographs and vellum", "engraved astronomical atlas illustration", "minimalist geometric poster art", "macro photograph of an impossible material", "cyanotype print with dense shadows", "worn instant-film photograph", "monumental architectural model photographed in fog"],
}

COMPOSITIONS = [
    "extreme close-up of one unsettling detail", "distant wide shot with the setting dominating", "low angle looking upward", "overhead view looking straight down",
    "framed within a doorway or window", "composition seen through a mirror reflection", "empty setting with no visible people", "off-centre composition with deep negative space",
    "foreground obstruction partially hiding the subject", "compressed long-lens view across the space", "symmetrical corridor perspective", "tilted frame with restrained unease",
]

ANOMALY_TREATMENTS = [
    "the anomaly is almost hidden at the edge of the frame", "only a physical trace remains after the event", "an impossible shadow reveals what is absent", "the anomaly is caught actively unfolding",
    "the setting subtly bends around the anomaly", "a reflection shows the anomaly before it appears", "one ordinary object is inexplicably displaced", "the anomaly is suggested by an empty space",
    "a repeating detail hints that reality has slipped", "the anomaly appears distant and easy to overlook", "a light reveals the anomaly for an instant", "the scene looks ordinary until one detail is noticed",
]

DETAILS = [
    "a small object placed where it should not be", "water beading upward along a surface",
    "dust disturbed in a precise human-shaped outline", "one light source casting two shadows",
    "a faint reflection that does not match the room", "a paper-thin gap of darkness in a solid wall",
    "repeated objects with one subtle difference", "a curtain moving in a sealed room",
    "an open drawer containing only damp air and condensation", "a clock face with no hands",
    "a footprint stopping in the middle of a clean floor", "a patch of frost in warm humid air",
    "a door chain hanging taut with nobody outside", "a chair turned toward an empty corner",
    "a phone screen glowing with no visible device", "a narrow beam of light ending abruptly",
    "a row of windows with one interior that is too deep", "a thin line of salt broken from the inside",
    "a familiar object scaled slightly too large", "a shadow crossing the scene without a visible source",
]

SHOTS = [
    "wide establishing shot, a small figure dwarfed by the space",
    "low-angle shot looking up",
    "over-the-shoulder view from behind a figure",
    "extreme close-up of a single unsettling object",
    "framed through a doorway or window, voyeuristic",
    "high-angle overhead view looking down",
    "symmetrical one-point perspective down a corridor",
    "silhouette against a bright light source",
    "reflection seen in a mirror, glass or puddle",
    "long-lens compressed view across a street",
    "tilted dutch angle",
    "medium shot of a figure seen from behind",
]

LIGHTS = [
    "a single bare bulb",
    "a flickering fluorescent tube",
    "moonlight through window blinds",
    "phone or monitor glow in the dark",
    "sodium streetlight haze",
    "candle and lantern light",
    "pre-dawn blue mist",
    "harsh midday sun with hard shadows",
    "vending-machine or refrigerator glow",
    "headlights sweeping through fog",
    "overcast flat daylight",
    "television static light",
]

MOODS = {
    "grounded": "grounded and realistic, nothing overtly supernatural",
    "slightly_unreal": "subtly wrong, something is slightly off",
    "supernatural": "an eerie, otherworldly presence",
    "reality_bending": "reality bending at the edges, impossible geometry",
    "mythic": "ancient, mythic weight and scale",
    "conceptual": "abstract and symbolic, an idea made visible",
}

SETTINGS = {
    "3": [
        "a narrow village alley at night",
        "an old temple courtyard in the rain",
        "a family altar room in an old apartment",
        "a rural cemetery path before dawn",
        "a traditional Taiwanese courtyard house at night",
        "a roadside earth-god shrine",
    ],
    "6": [
        "a Taiwanese apartment stairwell",
        "an empty night-market lane after closing",
        "a convenience store at 3 a.m.",
        "a mountain road tunnel",
        "a government office corridor after hours",
        "a rainy riverside bike path",
    ],
    "9": [
        "a windowless archive room",
        "an empty overpass over a motorway at dawn",
        "a hospital corridor with one light on",
        "a vast reclaimed-land industrial zone",
        "a server room humming in the dark",
        "a coastal fishing harbour in fog",
    ],
}

MOTIFS = {
    "possession": ["a person standing perfectly still with their back to the camera", "a shadow that does not match the body casting it"],
    "haunting": ["a figure-shaped stain spreading on a wall", "a half-open door with darkness behind it"],
    "ritual": ["paper talismans and burning incense", "a red thread tied between old wooden beams"],
    "curse": ["a small altar with offerings that have rotted", "a knotted red string hanging in still air"],
    "mediumship": ["a spirit medium's table with candles and bowls of rice", "an empty chair set out for someone"],
    "ancestral_sin": ["rows of old ancestral tablets in lamplight", "a family photograph with one face worn away"],
    "spirit_contract": ["two cups of tea, only one of them steaming", "a blank paper sheet and an ink stone under a lamp"],
    "exorcism": ["a ring of salt on a wooden floor", "bells and talismans trembling without wind"],
    "afterlife_glimpse": ["a corridor of mist ending in a pale doorway", "a staircase descending into soft white light"],
    "folk_belief": ["a roadside shrine with offerings in the rain", "paper lanterns swaying in still air"],
    "psychological": ["a room slightly too large for its furniture", "a person reflected in a dark window who is not mirroring them"],
    "urban_legend": ["a stairwell light that only works between floors", "a taxi parked alone in an empty lane at night"],
    "supernatural": ["a pale figure at the edge of a streetlight", "footprints appearing on a dusty floor"],
    "crime": ["evidence markers on wet pavement", "a dim interview room with one chair pulled out"],
    "suspense": ["a hallway where every door is slightly ajar", "a ringing phone in an empty house"],
    "identity_horror": ["a row of people all seen only from behind", "a mirror reflecting a different room"],
    "sci_fi_horror": ["a humming lab with an empty containment glass", "a corridor of status LEDs blinking out of sequence"],
    "surveillance_horror": ["a wall of CCTV monitors showing the same empty room", "a camera dome reflecting a figure that is not there"],
    "unknown_phenomenon": ["a pale unexplained light over apartment blocks", "power lines humming over a deserted street"],
    "reality_horror": ["a street where the buildings repeat", "a doorway that opens onto the same room"],
    "cognitive_hazard": ["an abstract repeating pattern the eye cannot leave", "people staring at the same blank wall"],
    "memetic": ["many identical phone screens glowing in a dark room", "a crowd all facing the same direction"],
    "ontological": ["a staircase that folds back onto itself", "furniture floating motionless in a bright void"],
    "cosmic_horror": ["a vast shape above a small coastal town", "an enormous door set into a cliff face"],
    "body_horror_extreme": ["hospital sheets shaped like someone who is not there", "fungus spreading over old furniture"],
    "time_loop": ["the same table setting repeated in several identical rooms", "one stairwell shown twice at once"],
    "forbidden_knowledge": ["a sealed archive of blank folders", "a closed book glowing at its edges"],
    "apocalyptic": ["an empty city street at dawn with abandoned cars", "an ash-coloured sky over a quiet harbour"],
}

ROLE_GUIDE_BASE = {
    "cover": "a title-led cover illustration: depict the exact person, object, place, or event named by the story title as the unmistakable focal subject. The title is the source of truth; do not substitute a generic horror motif or a scene unrelated to the title. Evoke the story without explaining the plot.",
    "scene": "the most striking moment of the story: the anomaly caught mid-moment in its setting.",
}
ROLE_GUIDE_EXTENDED = {
    "cover": ROLE_GUIDE_BASE["cover"],
    "scene_open": "the opening: the ordinary place and who is in it, with only a faint hint that something is off.",
    "scene": "the escalation: the first clearly impossible detail, caught mid-moment.",
    "scene_end": "the final disturbing image, or the quiet aftermath the ending implies.",
}

CJK = re.compile(r"[㐀-鿿豈-﫿]")
HEADING = re.compile(r"^第[〇零一二三四五六七八九十百\d]+[章節幕部]\s*[｜|:：]")
SUFFIX = "No text, no letters, no logos, no watermark. Well exposed with visible detail in the shadows."


class _Paragraphs(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.items: list[str] = []
        self._depth = 0
        self._buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "p":
            if self._depth == 0:
                self._buf = []
            self._depth += 1

    def handle_endtag(self, tag):
        if tag == "p" and self._depth:
            self._depth -= 1
            if self._depth == 0:
                text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
                if text:
                    self.items.append(text)

    def handle_data(self, data):
        if self._depth:
            self._buf.append(data)


def story_paragraphs(content: object) -> list[str]:
    """Readable paragraphs of the story HTML, without chapter-heading paragraphs."""
    parser = _Paragraphs()
    parser.feed(content if isinstance(content, str) else "")
    parser.close()
    return [p for p in parser.items if not HEADING.match(p)]


def story_beats(story: dict) -> dict[str, str]:
    """Pick an opening, a turning-point and a climax paragraph (short excerpts)."""
    paragraphs = story_paragraphs(story.get("content", ""))
    if not paragraphs:
        return {}
    beats = {}
    for name, fraction in (("opening", 0.12), ("turning point", 0.55), ("climax", 0.92)):
        index = min(len(paragraphs) - 1, int(len(paragraphs) * fraction))
        # Prefer a paragraph with some substance; look a few ahead if this one is a one-liner.
        for candidate in range(index, min(len(paragraphs), index + 4)):
            if len(paragraphs[candidate]) >= 40:
                index = candidate
                break
        beats[name] = paragraphs[index][:260]
    return beats


def _pick_variety(code: str, seed: object, cat: str, count: int) -> dict:
    rng = random.Random(f"{code}|{seed}|{cat}|visual")
    genres = list(GENRES.get(cat, GENRES["6"]))
    # Preserve the established story-specific looks as additional options.
    genres.extend(LOOKS.get(cat, LOOKS["6"]))
    return {
        "palettes": rng.sample(PALETTES.get(cat, PALETTES["6"]), count),
        "genre": rng.sample(genres, count),
        "composition": rng.sample(COMPOSITIONS, count),
        "anomaly": rng.sample(ANOMALY_TREATMENTS, count),
        "details": rng.sample(DETAILS, count),
        "shots": rng.sample(SHOTS, count),
        "lights": rng.sample(LIGHTS, count),
    }


def _clean_scene(text: object, limit: int = 380) -> str:
    """Accept only English text (image models follow it far better); trim at a sentence."""
    if not isinstance(text, str):
        return ""
    text = re.sub(r"\s+", " ", text).strip().strip("\"'“”")
    if not text or len(CJK.findall(text)) > max(2, int(len(text) * 0.1)):
        return ""
    if len(text) > limit:
        cut = text[:limit]
        stop = max(cut.rfind(". "), cut.rfind("; "))
        text = cut[: stop + 1] if stop > limit // 2 else cut.rstrip(" ,;")
    return text.rstrip(".")


def build_brief_request(story: dict, kinds: tuple, variety: dict, beats: dict) -> tuple[str, str]:
    """System and user prompt asking a text model for English scene descriptions."""
    guide = ROLE_GUIDE_EXTENDED if kinds == EXTENDED_KINDS else ROLE_GUIDE_BASE
    analysis = story.get("director_analysis") if isinstance(story.get("director_analysis"), dict) else {}
    plan_lines = []
    for index, kind in enumerate(kinds):
        plan_lines.append(
            f'- kind "{kind}": {guide[kind]} Camera: {variety["shots"][index]}. '
            f'Composition: {variety["composition"][index]}. Light: {variety["lights"][index]}. '
            f'Visual genre: {variety["genre"][index]}. Anomaly treatment: {variety["anomaly"][index]}.'
        )
    beat_lines = "\n".join(f"- {name}: {text}" for name, text in beats.items()) or "- (no excerpt available)"
    system = (
        "You are a film director and concept artist writing image prompts for a horror story archive. "
        "Reply with a single JSON object only. Write in English only, even though the story is in Chinese."
    )
    user = f"""Story title (PRIMARY visual brief; depict its specific subject): {story.get('title', '')}
Summary: {story.get('summary', '')}
Anomaly: {analysis.get('anomaly_core', '')}
Characters: {analysis.get('character_core', '')}
Rule of the anomaly: {analysis.get('internal_rule', '')}
Story beats (Chinese excerpts):
{beat_lines}

Write one concrete image description per kind below. Each must show something the camera could actually see.
{chr(10).join(plan_lines)}

Rules for every description:
- 1-2 sentences, at most 60 words, English only, describing who or what is visible, where, and the one thing that is wrong.
- One clear focal point. Use the camera and light given for that kind so the scene is consistent with them.
- Ground the setting in the story (Taiwan or East Asia unless the story clearly says otherwise). Anonymous people only; no real people, brands or logos.
- Prefer figures seen from behind, in silhouette, or partly hidden, and hands, objects and places over frontal close-up faces.
- Nothing graphic: no gore, no open wounds. No readable text, signs or writing anywhere in the image.
- Do not repeat the same subject or composition between kinds.
- For "cover", the scene must visibly represent the specific subject named in Story title. Treat title nouns and named objects/places as required visual anchors; summary and beats may add detail but must never replace or contradict the title. Do not use a generic motif as the cover subject.

JSON format: {{"images":[{{"kind":"<kind>","scene":"<description>"}}]}}"""
    return system, user


def _fallback_scene(kind: str, story: dict, cat: str, rng: random.Random) -> str:
    types = [t for t in story.get("horror_type", []) if t in MOTIFS] or ["unknown_phenomenon"]
    first = rng.choice(MOTIFS[types[0]])
    other_pool = MOTIFS[types[-1]] if len(types) > 1 else MOTIFS[types[0]]
    second = rng.choice([m for m in other_pool if m != first] or other_pool)
    setting = rng.choice(SETTINGS.get(cat, SETTINGS["6"]))
    if kind == "cover":
        title = re.sub(r"\s+", " ", str(story.get("title") or "")).strip()
        if title:
            return f"A title-led cover illustration directly depicting the specific subject of the story title '{title}', with that subject as the unmistakable focal point; do not substitute a generic horror motif"
        return f"A symbolic key image directly representing the story's central subject: {first}"
    if kind == "scene_open":
        return f"{setting[0].upper()}{setting[1:]}, ordinary at first glance, with a faint sign of {first}"
    if kind == "scene_end":
        return f"The silent aftermath in {setting}: {second}"
    return f"{first[0].upper()}{first[1:]}, caught mid-moment in {setting}"


def plan_images(
    story: dict,
    cat: str,
    dice: dict,
    ask: Optional[Callable[[str, str], Optional[dict]]] = None,
    extra_scenes: bool = False,
) -> list[dict]:
    """Return ``[{"kind", "prompt", "source"}]`` for the images of one story.

    ``ask(system, user)`` should return a parsed JSON object (or None). Any failure or
    unusable answer falls back to the rule-based scene text for the affected kinds.
    """
    kinds = EXTENDED_KINDS if extra_scenes else BASE_KINDS
    code = str(story.get("story_code") or story.get("source_hash") or "story")
    seed = story.get("dice_seed", dice.get("dice_seed", 0))
    variety = _pick_variety(code, seed, cat, len(kinds))
    mood = MOODS.get(story.get("fantasy_level") or dice.get("fantasy_level"), "")

    scenes: dict[str, str] = {}
    if ask is not None:
        try:
            system, user = build_brief_request(story, kinds, variety, story_beats(story))
            brief = ask(system, user)
            items = brief.get("images") if isinstance(brief, dict) else None
            for item in items if isinstance(items, list) else []:
                if isinstance(item, dict) and item.get("kind") in kinds:
                    text = _clean_scene(item.get("scene"))
                    if text:
                        scenes[item["kind"]] = text
        except Exception:  # the caller logs provider problems; images must never block a story
            scenes = {}

    rng = random.Random(f"{code}|{seed}|fallback")
    plan = []
    for index, kind in enumerate(kinds):
        source = "llm" if kind in scenes else "fallback"
        scene = scenes.get(kind) or _fallback_scene(kind, story, cat, rng)
        shot = variety["shots"][index]
        parts = [
            scene.rstrip(".") + ".",
            shot[0].upper() + shot[1:] + ".",
            f"Lit by {variety['lights'][index]}.",
            f"Colour palette: {variety['palettes'][index]}.",
            f"Composition: {variety['composition'][index]}.",
            f"Anomaly presentation: {variety['anomaly'][index]}.",
            f"Distinctive visual detail: {variety['details'][index]}.",
            variety["genre"][index][0].upper() + variety["genre"][index][1:] + ".",
        ]
        if mood:
            parts.append(mood[0].upper() + mood[1:] + ".")
        parts.append(SUFFIX)
        plan.append({"kind": kind, "prompt": " ".join(parts)[:1200], "source": source})
    return plan


