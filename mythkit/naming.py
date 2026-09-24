"""Turn a free-text "describe your world" prompt into a pool of thematic,
guaranteed-unique sound names in the style real producers use, e.g.

    740 808 CHARIOT.wav
    808 - Alicemagic [MISOGI].wav
    HG CLAP 1.wav

We land on "{TAG} - {WORD}" as the output format (matches the most common
convention across real kits), where WORD is drawn from a theme-matched word
bank blended with words the user typed themselves, so the vibe always
traces back to what they described.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

# Each bank: nouns are used standalone first ("ZEUS"); adjectives only get
# used once nouns run out, as "ADJ NOUN" pairs, to keep single-word names
# the common case (that's what most real kits do).
THEME_BANKS: dict[str, dict[str, list[str]]] = {
    "greek": {
        "keywords": ["greek", "olympus", "olympian", "titan", "mythology", "myth", "zeus", "hades"],
        "nouns": [
            "ZEUS", "HADES", "CHARIOT", "OLYMPUS", "TITAN", "MEDUSA", "ICARUS", "ATLAS",
            "PANDORA", "NEMESIS", "ELYSIUM", "CHAOS", "NYX", "ARES", "HERA", "APOLLO",
            "ATHENA", "POSEIDON", "HERMES", "PERSEPHONE", "MINOTAUR", "SIREN", "CYCLOPS",
            "HYDRA", "STYX", "TARTARUS", "CENTAUR", "GORGON", "HELIOS", "SELENE", "EROS",
            "THANATOS", "HUBRIS", "LABYRINTH", "ORACLE", "SPARTA", "KRONOS",
        ],
        "adjectives": ["DIVINE", "IMMORTAL", "SACRED", "GODLY", "ETERNAL", "FALLEN"],
    },
    "norse": {
        "keywords": ["norse", "viking", "odin", "valhalla", "asgard"],
        "nouns": [
            "ODIN", "THOR", "LOKI", "VALHALLA", "ASGARD", "VALKYRIE", "RAGNAROK", "FENRIR",
            "YGGDRASIL", "MIDGARD", "FREYA", "BIFROST", "MJOLNIR", "RUNE", "DRAUGR",
        ],
        "adjectives": ["FROSTBOUND", "ANCIENT", "WARBORN"],
    },
    "egyptian": {
        "keywords": ["egypt", "egyptian", "pharaoh", "pyramid", "anubis"],
        "nouns": [
            "ANUBIS", "OSIRIS", "ISIS", "RA", "PHARAOH", "SPHINX", "NILE", "SCARAB",
            "PYRAMID", "HIEROGLYPH", "MUMMY", "OBELISK", "HORUS", "NEFERTITI",
        ],
        "adjectives": ["SACRED", "BURIED", "ETERNAL"],
    },
    "anime": {
        "keywords": ["anime", "manga", "japan", "japanese", "otaku", "tokyo"],
        "nouns": [
            "SENSEI", "RONIN", "KATANA", "SHOGUN", "SAMURAI", "KAIJU", "YOKAI", "ONI",
            "DOJO", "KITSUNE", "SHINIGAMI", "SAKURA", "BUSHIDO", "IREZUMI", "SATORI",
            "ZANSHIN", "NEKO", "TENGU", "RYUJIN", "AMATERASU", "SUSANOO", "HANNYA",
            "MUSHIN", "GENSO",
        ],
        "adjectives": ["ROGUE", "SILENT", "CRIMSON", "HOLLOW"],
    },
    "cyberpunk": {
        "keywords": ["cyberpunk", "cyber", "futuristic", "sci-fi", "scifi", "tech", "robot", "ai", "hacker", "neon", "matrix"],
        "nouns": [
            "NEON", "CHROME", "GLITCH", "STATIC", "VOID", "NETRUNNER", "GHOSTWIRE",
            "SYNTH", "HOLOGRAM", "CIRCUIT", "BYTE", "VAPOR", "OVERCLOCK", "FIREWALL",
            "MAINFRAME", "ANDROID", "CYBORG", "IMPLANT", "DATASTREAM", "PIXEL", "LASER",
            "PLASMA", "REBOOT", "BLACKOUT", "SIGNAL", "NANITE", "UPLINK",
        ],
        "adjectives": ["DIGITAL", "SYNTHETIC", "ROGUE", "ENCRYPTED"],
    },
    "space": {
        "keywords": ["space", "galaxy", "cosmic", "astro", "planet", "alien", "stars", "universe"],
        "nouns": [
            "NOVA", "NEBULA", "COMET", "GALAXY", "ORBIT", "LUNAR", "SOLAR", "COSMOS",
            "METEOR", "ASTRO", "ECLIPSE", "STARDUST", "QUASAR", "PULSAR", "ANDROMEDA",
            "VOYAGER", "ZENITH", "HORIZON", "GRAVITY", "SUPERNOVA",
        ],
        "adjectives": ["INTERSTELLAR", "DISTANT", "INFINITE"],
    },
    "horror": {
        "keywords": ["horror", "gothic", "scary", "demon", "vampire", "ghost", "monster", "dark"],
        "nouns": [
            "WRAITH", "PHANTOM", "SPECTRE", "REAPER", "CRYPT", "HOLLOW", "NIGHTMARE",
            "VOODOO", "BANSHEE", "GHOUL", "CURSED", "HAUNTED", "ABYSS", "DREAD", "OMEN",
            "SORROW", "REQUIEM", "TOMBSTONE",
        ],
        "adjectives": ["CURSED", "HAUNTED", "WICKED", "UNDEAD"],
    },
    "nature": {
        "keywords": ["nature", "forest", "elements", "earth", "wild", "jungle", "mountain"],
        "nouns": [
            "WILDFIRE", "THUNDER", "FROST", "EMBER", "STORM", "TIDE", "GLACIER", "AURORA",
            "MONSOON", "WILDROSE", "BLOOM", "THORN", "DROUGHT", "CYCLONE", "AVALANCHE",
        ],
        "adjectives": ["WILD", "UNTAMED", "ANCIENT"],
    },
    "ocean": {
        "keywords": ["ocean", "sea", "water", "underwater", "aquatic", "wave"],
        "nouns": [
            "TSUNAMI", "CORAL", "RIPTIDE", "MAELSTROM", "LEVIATHAN", "KRAKEN", "TRENCH",
            "UNDERTOW", "DRIFT", "ABYSS", "TIDEPOOL", "CURRENT",
        ],
        "adjectives": ["DEEP", "DROWNED", "SUNKEN"],
    },
    "urban": {
        "keywords": ["urban", "street", "city", "hood", "trap", "block"],
        "nouns": [
            "HUSTLE", "CONCRETE", "SKYLINE", "GRIDLOCK", "ALLEY", "SUBWAY", "NEONLIGHT",
            "GRAFFITI", "HEIST", "MIDNIGHT", "BLOCK", "CURFEW",
        ],
        "adjectives": ["RAW", "GRIMY", "RESTLESS"],
    },
    "fantasy": {
        "keywords": ["fantasy", "magic", "medieval", "dragon", "kingdom", "wizard", "sorcery"],
        "nouns": [
            "DRAGON", "WIZARD", "ENCHANT", "MYSTIC", "REALM", "KINGDOM", "SORCERY",
            "RUNE", "ELIXIR", "CRYSTAL", "PHOENIX", "GRIMOIRE", "ETHEREAL", "CELESTIAL",
        ],
        "adjectives": ["ENCHANTED", "FORBIDDEN", "ANCIENT"],
    },
    "love": {
        "keywords": ["love", "heartbreak", "romance", "limerence", "crush", "emotional", "lonely", "heart"],
        "nouns": [
            "LIMERENCE", "HEARTBREAK", "INFATUATION", "LONGING", "OBSESSION", "CRUSH",
            "YEARNING", "SWOON", "DESIRE", "ACHE", "NOSTALGIA", "INTOXICATED",
            "ROSEWATER", "LOVESICK", "DREAMSTATE", "EUPHORIA", "HALCYON", "BUTTERFLIES",
        ],
        "adjectives": ["TENDER", "LOVESICK", "FADED", "INTOXICATED"],
    },
}

# Always mixed in a little, regardless of theme — a safety net that keeps
# names sounding cool even for very sparse or totally novel prompts.
UNIVERSAL_NOUNS = [
    "ORACLE", "MIRAGE", "ECLIPSE", "PHANTOM", "VELVET", "CIPHER", "ONYX", "EMBER",
    "HALO", "RELIC", "VERTEX", "LUMEN", "ECHO", "ZENITH", "WRAITH", "NOVA",
]
UNIVERSAL_ADJECTIVES = [
    "PRIME", "ULTRA", "RAW", "GOLD", "DARK", "PURE", "ETERNAL", "SUPREME", "SACRED",
    "ROYAL", "DIVINE", "FERAL", "SAVAGE", "FROZEN", "BURNING", "SILENT", "HIDDEN",
    "LOST", "FADED", "GHOST", "TWIN", "FINAL", "ANCIENT", "FORBIDDEN", "WILD",
]

_STOPWORDS = {
    "a", "an", "the", "of", "and", "or", "with", "in", "on", "my", "is", "are",
    "to", "for", "world", "theme", "themes", "vibe", "vibes", "im", "i'm", "its",
}
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]{2,}")

CATEGORY_TAGS = {
    "808": "808",
    "kick": "KICK",
    "snare": "SNARE",
    "clap": "CLAP",
    "hihat_closed": "HIHAT",
    "hihat_open": "OPEN HAT",
    "percussion": "PERC",
    "fx": "FX",
    "vox": "VOX",
}


def _extract_user_words(world_text: str) -> list[str]:
    words = []
    for match in _WORD_RE.finditer(world_text):
        w = match.group(0)
        if w.lower() in _STOPWORDS:
            continue
        words.append(w.upper())
    # de-dupe, keep order
    seen = set()
    out = []
    for w in words:
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out


def match_theme_banks(world_text: str) -> list[str]:
    text = world_text.lower()
    matched = []
    for key, bank in THEME_BANKS.items():
        if any(kw in text for kw in bank["keywords"]):
            matched.append(key)
    return matched


_STYLES = ["lower", "upper", "camel", "first_lower_rest_upper", "spark", "wrapped"]
_STYLE_WEIGHTS = [3, 2, 2, 2, 3, 1]


def _stylize(phrase: str, rng: random.Random) -> str:
    """Underground-kit casing: deliberately inconsistent, not clean Title
    Case — some names fully lowercase, some ALL CAPS, some with a random
    letter or two capitalized mid-word, some CamelCase mashups. Matches
    the "doesn't quite look right on purpose" style real underground kits
    use (blickout, FrozenLOTUS, hollowW, xdojox, ...).
    """
    words = phrase.split(" ")
    choices = _STYLES if len(words) > 1 else [s for s in _STYLES if s != "camel"]
    weights = [_STYLE_WEIGHTS[_STYLES.index(s)] for s in choices]
    style = rng.choices(choices, weights=weights, k=1)[0]

    if style == "upper":
        return phrase.upper()

    if style == "camel":
        return "".join(w.capitalize() for w in words)

    if style == "first_lower_rest_upper":
        lowered = phrase.lower()
        return lowered if len(lowered) <= 1 else lowered[0] + lowered[1:].upper()

    if style == "spark":
        chars = list(phrase.lower())
        letter_idx = [i for i, c in enumerate(chars) if c.isalpha()]
        if letter_idx:
            n_sparks = 1 if len(letter_idx) <= 4 else rng.randint(1, 2)
            for i in rng.sample(letter_idx, k=min(n_sparks, len(letter_idx))):
                chars[i] = chars[i].upper()
        return "".join(chars)

    if style == "wrapped":
        return f"x{phrase.lower().replace(' ', '')}x"

    return phrase.lower()


@dataclass
class NamePool:
    nouns: list[str]
    adjectives: list[str]
    rng: random.Random
    used: set[str] = field(default_factory=set)

    def _try_use(self, candidate: str) -> str | None:
        c = candidate.strip().upper()
        if c and c not in self.used:
            self.used.add(c)
            return c
        return None

    def _next_canonical(self) -> str:
        # 1. Plain noun.
        shuffled_nouns = self.nouns[:]
        self.rng.shuffle(shuffled_nouns)
        for n in shuffled_nouns:
            got = self._try_use(n)
            if got:
                return got

        # 2. ADJ NOUN combo.
        combos = [(a, n) for a in self.adjectives for n in self.nouns]
        self.rng.shuffle(combos)
        for a, n in combos:
            got = self._try_use(f"{a} {n}")
            if got:
                return got

        # 3. Numbered fallback — guarantees we never fail to produce a name.
        base = self.rng.choice(self.nouns) if self.nouns else "SOUND"
        i = 2
        while True:
            got = self._try_use(f"{base} {i}")
            if got:
                return got
            i += 1

    def next_name(self) -> str:
        # Uniqueness is tracked on the canonical (uppercase) form so two
        # differently-cased renders of the same word never both get used;
        # the underground casing is purely a final display transform.
        return _stylize(self._next_canonical(), self.rng)


def build_name_pool(world_text: str, producer_name: str) -> NamePool:
    matched = match_theme_banks(world_text)
    seed_text = f"{producer_name}|{world_text}|{','.join(matched)}"
    rng = random.Random(seed_text)

    nouns: list[str] = []
    adjectives: list[str] = []
    for key in matched:
        bank = THEME_BANKS[key]
        nouns.extend(bank["nouns"])
        adjectives.extend(bank.get("adjectives", []))

    nouns.extend(_extract_user_words(world_text))
    nouns.extend(UNIVERSAL_NOUNS)
    adjectives.extend(UNIVERSAL_ADJECTIVES)

    # de-dupe while preserving order
    nouns = list(dict.fromkeys(n for n in nouns if n))
    adjectives = list(dict.fromkeys(a for a in adjectives if a))

    return NamePool(nouns=nouns, adjectives=adjectives, rng=rng)
