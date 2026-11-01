"""Offline original-hero suggestions. Every suggestion is screened by the protected-name check."""
from __future__ import annotations

import random

from .ip_guard import find

FIRST = ["Captain", "Professor", "Agent", "Little", "Major", "Doctor", "Sergeant", "Lady", "Sir", "Kid"]
# Name parts avoid known comic/cartoon character names; still search any name before publishing.
CORE = ["Tidal", "Pebble", "Thunderpaw", "Sprocket", "Zephyr", "Coral", "Bramble", "Pixel", "Marble", "Breeze",
        "Puddlefoot", "Cinderbell", "Dandelion", "Biscuit", "Kelpie", "Whirligig", "Gumdrop", "Tumbleweed"]
SOLO = ["Gale Runner", "Puddle Jumper", "Sky Sprout", "Glow Guard", "Stormkite", "Rainbow Rook",
        "Turbo Toad", "Captain Cumulus", "Wavecrest", "Gearheart", "Peppermint Patrol", "Firefly Finn"]
POWERS = ["can fly on gusts of wind", "talks to animals", "makes bouncy force-bubbles", "runs as fast as a cheetah",
          "grows plants instantly", "controls friendly ocean waves", "shrinks to the size of a ladybug", "glows to light up the dark",
          "builds gadgets from junk", "lifts heavy things with one hand", "can turn invisible for ten seconds", "makes rainbows appear"]
COSTUMES = ["a zip-up suit with big star-shaped buttons", "a hooded cape with a scalloped edge", "goggles, a scarf and chunky boots",
            "a vest covered in tool pockets", "a wavy-hemmed tunic and wrist cuffs", "a helmet with round ear-fins",
            "a puffy jacket with lightning-bolt stripes", "a leaf-patterned cloak and sandals"]
EMBLEMS = ["a smiling sun", "a paper airplane", "a seashell", "a leaf inside a circle", "three dots in a triangle",
           "a wave crest", "a gear with a heart in the middle", "a crescent moon with a star", "a pinwheel", "a kite"]
ROLES = ["leader", "flier", "speedster", "inventor", "strongest member", "scout", "healer", "sidekick"]
TEAM_A = ["Sunny", "Tidepool", "Pocket", "Rainbow", "Bright", "Cloud", "Compass", "Seashell", "Maple", "Puddle"]
TEAM_B = ["Squad", "Patrol", "Crew", "Brigade", "Helpers", "Club", "Rescue Squad", "Helper Club"]


def _clean(name: str) -> bool:
    return not find(name)


def suggest_hero(seed: int | None = None, taken: set[str] | None = None) -> dict:
    rnd = random.Random(seed)
    taken = {t.lower() for t in (taken or set())}
    for _ in range(200):
        name = rnd.choice(SOLO) if rnd.random() < 0.35 else f"{rnd.choice(FIRST)} {rnd.choice(CORE)}"
        if name.lower() not in taken and _clean(name):
            break
    return {"name": name, "role": rnd.choice(ROLES), "powers": rnd.choice(POWERS), "costume": rnd.choice(COSTUMES),
            "emblem": rnd.choice(EMBLEMS), "appearance": "", "proportions": "head about 1/4 of body height", "reference_asset_ids": []}


def suggest_team(seed: int | None = None) -> dict:
    rnd = random.Random(seed)
    for _ in range(100):
        name = f"The {rnd.choice(TEAM_A)} {rnd.choice(TEAM_B)}"
        if _clean(name):
            break
    return {"name": name, "motto": rnd.choice(["Kind hearts, brave hands!", "Together we shine!", "Help first, high-five later!",
                                                  "Small heroes, big courage!"]),
            "headquarters": rnd.choice(["a treehouse fortress", "a lighthouse on a rocky island", "a cloud-top observatory",
                                        "an underwater bubble base", "a converted school bus"]),
            "emblem": rnd.choice(EMBLEMS)}
