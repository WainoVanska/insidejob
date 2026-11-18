"""Turn a plain-words `looking_for:` block into filters and ranking rules.

    looking_for:
      roles: [intern, thesis, junior, graduate]   # default: all four
      cities: [Helsinki, Espoo]
      country: Finland
      remote: true            # true = EU/Europe/EMEA/Nordics remote; "anywhere" = any remote
      interests: [graphics, AI, games]
      start: summer 2027

`build(looking_for)` returns `{"filters": {...}, "rank": {...}}` in the same shape a
hand-written config uses, so the normal validation in `config.py` checks the result and
explicit `filters:` / `rank:` keys can replace any generated part, key by key.

Scoring (max 13, same scale as the hand-written example):
    title      intern 3, thesis 3, junior 2, graduate 1 (only the roles asked for)
    location   a city 3, the country 2, remote 1; a job with no location gets 2 if a
               country is given (local companies), 1 with only cities, else 0
    interests  3 in the title, half if only in the description; company boilerplate
               words (AI, data, cloud, agile…) count in the title only
    start      +2 when the job starts in the season or month asked for
"""

import re
from typing import Any

from insidejob.rank import words_pattern


class ProfileError(ValueError):
    """`looking_for:` can't be understood; the message says why in plain words."""


ROLE_PATTERNS = {
    "intern": (
        r"\b(interns?|internships?|trainees?|traineeship|summer|working student"
        r"|apprentice(ship)?)\b|kesä|harjoittel"
    ),
    "thesis": r"\bthesis\b|opinnäyte|diplomityö",
    "junior": r"\b(junior|entry[- ]level)\b",
    "graduate": r"\b(graduates?|new grads?)\b",
}
ROLE_POINTS = {"intern": 3, "thesis": 3, "junior": 2, "graduate": 1}
ROLES = tuple(ROLE_PATTERNS)

SENIOR = r"\b(senior|sr|lead|principal|staff|director|manager|head of|vp|vice president|chief)\b"
EU_REMOTE = ["EU", "Europe", "EMEA", "Nordics", "Nordic"]

# The name the user writes -> every name a job board may use for the country.
COUNTRIES = {
    "finland": ["Finland", "Suomi"],
    "sweden": ["Sweden", "Sverige"],
    "norway": ["Norway", "Norge"],
    "denmark": ["Denmark", "Danmark"],
    "iceland": ["Iceland", "Ísland"],
    "estonia": ["Estonia", "Eesti"],
    "latvia": ["Latvia", "Latvija"],
    "lithuania": ["Lithuania", "Lietuva"],
    "germany": ["Germany", "Deutschland"],
    "netherlands": ["Netherlands", "Nederland", "Holland"],
    "poland": ["Poland", "Polska"],
    "france": ["France"],
    "spain": ["Spain", "España"],
    "portugal": ["Portugal"],
    "italy": ["Italy", "Italia"],
    "ireland": ["Ireland"],
    "austria": ["Austria", "Österreich"],
    "switzerland": ["Switzerland", "Schweiz", "Suisse"],
    "belgium": ["Belgium", "België", "Belgique"],
    "czechia": ["Czechia", "Czech Republic"],
    "united kingdom": ["United Kingdom", "UK", "England", "Scotland"],
    "united states": ["United States", "USA", "US"],
    "canada": ["Canada"],
}
COUNTRY_ALIASES = {
    "suomi": "finland",
    "sverige": "sweden",
    "norge": "norway",
    "danmark": "denmark",
    "eesti": "estonia",
    "deutschland": "germany",
    "holland": "netherlands",
    "the netherlands": "netherlands",
    "czech republic": "czechia",
    "uk": "united kingdom",
    "great britain": "united kingdom",
    "england": "united kingdom",
    "usa": "united states",
    "us": "united states",
}

# Words nearly every company repeats in its job ads ("we use AI to…", "data-driven",
# "cloud platform"): they only count when they're in the job title.
BOILERPLATE = {
    "ai",
    "data",
    "cloud",
    "agile",
    "digital",
    "innovation",
    "automation",
    "analytics",
    "platform",
    "sustainability",
    "design",
}

# Interest name -> words that mean it. An interest not listed here is used as written.
INTERESTS = {
    "graphics": [
        "graphics", "rendering", "renderer", "OpenGL", "Vulkan", "DirectX", "Metal",
        "shader", "shaders", "GLSL", "HLSL", "GPU", "GPUs", "3D", "computer graphics",
        "game engine", "game engines",
    ],
    "ai": [
        "AI", "artificial intelligence", "machine learning", "ML", "deep learning", "LLM",
        "LLMs", "generative AI", "GenAI", "NLP", "computer vision", "AI agents",
    ],
    "games": [
        "game", "games", "gaming", "gameplay", "game developer", "game design", "Unity",
        "Unreal",
    ],
    "web": [
        "web", "frontend", "front-end", "full stack", "full-stack", "fullstack", "React",
        "TypeScript", "JavaScript", "Vue", "Angular",
    ],
    "mobile": ["mobile", "iOS", "Android", "Swift", "Kotlin", "Flutter", "React Native"],
    "backend": [
        "backend", "back-end", "API", "APIs", "microservices", "Java", "Python", "Node.js",
        "Scala", ".NET", "C#",
    ],
    "software": ["software", "developer", "software engineer", "programming", "coding"],
    "data": [
        "data", "data science", "data scientist", "data engineer", "data engineering",
        "data analyst", "analytics", "SQL", "BI", "business intelligence",
    ],
    "cloud": [
        "cloud", "AWS", "Azure", "GCP", "DevOps", "Kubernetes", "Docker", "infrastructure",
        "SRE", "platform",
    ],
    "embedded": [
        "embedded", "firmware", "C++", "RTOS", "microcontroller", "microcontrollers", "FPGA",
        "hardware", "electronics",
    ],
    "security": [
        "security", "cybersecurity", "cyber security", "infosec", "penetration testing",
        "pentest", "SOC", "tietoturva", "kyberturvallisuus",
    ],
    "design": [
        "design", "designer", "UX", "UI", "user experience", "user interface", "Figma",
        "product design", "graphic design", "visual design",
    ],
    "marketing": [
        "marketing", "growth", "SEO", "content marketing", "social media", "brand",
        "communications", "markkinointi", "viestintä",
    ],
    "sales": [
        "sales", "account executive", "business development", "SDR", "BDR",
        "customer success", "myynti",
    ],
    "finance": [
        "finance", "financial", "accounting", "accountant", "controller", "audit",
        "FP&A", "treasury", "taloushallinto", "kirjanpito",
    ],
    "hr": ["HR", "human resources", "people operations", "recruiting", "recruitment", "talent"],
    "research": ["research", "researcher", "R&D", "scientist", "PhD"],
    "robotics": ["robotics", "robot", "robots", "ROS", "autonomous", "drones"],
}  # fmt: skip
INTEREST_ALIASES = {
    "artificial intelligence": "ai",
    "machine learning": "ai",
    "ml": "ai",
    "game": "games",
    "gaming": "games",
    "game development": "games",
    "frontend": "web",
    "front-end": "web",
    "web development": "web",
    "apps": "mobile",
    "back-end": "backend",
    "data science": "data",
    "devops": "cloud",
    "cybersecurity": "security",
    "ux": "design",
    "ui": "design",
    "computer graphics": "graphics",
    "rendering": "graphics",
}

# Seasons and months, English and Finnish, for `start:`.
MONTHS = (
    ("january", "tammi"), ("february", "helmi"), ("march", "maalis"), ("april", "huhti"),
    ("may", "touko"), ("june", "kesä"), ("july", "heinä"), ("august", "elo"),
    ("september", "syys"), ("october", "loka"), ("november", "marras"),
    ("december", "joulu"),
)  # fmt: skip
SEASONS = {  # season -> (Finnish word, month numbers 1-12)
    "spring": ("kevät|kevää", (3, 4, 5)),
    "summer": ("kesä", (5, 6, 7, 8)),
    "autumn": ("syksy", (9, 10, 11)),
    "fall": ("syksy", (9, 10, 11)),
    "winter": ("talvi|talve", (12, 1, 2)),
}
SEASON_ALIASES = {"kevät": "spring", "kesä": "summer", "syksy": "autumn", "talvi": "winter"}
START_POINTS = 2

KEYS = ("roles", "cities", "country", "remote", "interests", "start")


def build(value: Any) -> dict[str, dict[str, Any]]:
    """`looking_for:` -> {"filters": {...}, "rank": {...}} in config.yaml shape."""
    if not isinstance(value, dict):
        raise ProfileError("looking_for must be a mapping, e.g. `roles: [intern, junior]`")
    unknown = set(value) - set(KEYS)
    if unknown:
        raise ProfileError(f"unknown key(s) {sorted(unknown)} (allowed: {', '.join(KEYS)})")

    roles = _roles(value.get("roles"))
    cities = _words(value.get("cities"), "cities")
    countries = _country(value.get("country"))
    remote = _remote(value.get("remote"))
    remote_anywhere = "anywhere" in remote

    filters: dict[str, Any] = {
        "title": "|".join(ROLE_PATTERNS[role] for role in roles),
        "exclude": SENIOR,
    }
    # With `remote: true`, "Remote" alone doesn't pass ("Remote - United States" stays
    # out) but "Remote - EMEA" does; `remote: anywhere` lets every remote job in.
    place_words = cities + countries + [w for w in remote if remote_anywhere or w != "remote"]
    if place_words:
        filters["location"] = words_pattern(place_words).pattern

    location: list[dict[str, Any]] = []
    if cities:
        location.append({"points": 3, "words": cities})
    if countries:
        location.append({"points": 2, "words": countries})
    if remote:
        location.append({"points": 1, "words": remote})

    rank: dict[str, Any] = {
        "title": [
            {"points": ROLE_POINTS[role], "label": role, "match": ROLE_PATTERNS[role]}
            for role in roles
        ],
        "location": location,
        "unknown_location": 2 if countries else 1 if cities else 0,
        "interests": _interests(value.get("interests")),
        "start": _start(value.get("start")),
    }
    return {"filters": filters, "rank": rank}


def _roles(value: Any) -> list[str]:
    if value is None:
        return list(ROLES)
    names = [w.lower() for w in _words(value, "roles")]
    if not names:
        return list(ROLES)
    unknown = [n for n in names if n not in ROLE_PATTERNS]
    if unknown:
        raise ProfileError(f"roles: unknown {unknown}; choose from {', '.join(ROLES)}")
    return [role for role in ROLES if role in names]  # fixed order: best rule first


def _country(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if not isinstance(value, str):
        raise ProfileError("country must be one name, e.g. `country: Finland`")
    key = value.strip().lower()
    key = COUNTRY_ALIASES.get(key, key)
    return list(COUNTRIES.get(key, [value.strip()]))


def _remote(value: Any) -> list[str]:
    if value is None or value is False:
        return []
    if value is True:
        return ["remote", *EU_REMOTE]
    if isinstance(value, str) and value.strip().lower() == "anywhere":
        return ["remote", "anywhere", "worldwide", *EU_REMOTE]
    raise ProfileError(
        "remote must be true (remote within Europe), false, or anywhere (any remote job)"
    )


def _interests(value: Any) -> list[dict[str, Any]]:
    """One or two rules per interest: description-friendly words, and title-only words."""
    rules: list[dict[str, Any]] = []
    for name in _words(value, "interests"):
        key = name.lower()
        key = INTEREST_ALIASES.get(key, key)
        words = INTERESTS.get(key, [name])
        anywhere = [w for w in words if w.lower() not in BOILERPLATE]
        title_only = [w for w in words if w.lower() in BOILERPLATE]
        if anywhere:
            rules.append({"points": 3, "label": name, "words": anywhere})
        if title_only:
            rules.append({"points": 3, "label": name, "words": title_only, "title_only": True})
    return rules


def _start(value: Any) -> list[dict[str, Any]]:
    if value is None or value == "":
        return []
    texts = value if isinstance(value, list) else [value]
    rules = []
    for text in texts:
        if not isinstance(text, str | int):
            raise ProfileError("start must be text like `summer 2027` or `June 2027`")
        text = str(text).strip()
        rules.append({"points": START_POINTS, "label": text, "match": start_pattern(text)})
    return rules


def start_pattern(text: str) -> str:
    """'summer 2027' -> a regex for summer/kesä 2027 and May-Aug 2027, in EN and FI.

    Also takes a single month ('June 2027', 'kesäkuu 2027') and seasons or months
    without a year ('summer').
    """
    m = re.fullmatch(r"\s*([^\W\d]+)\s*(20\d\d)?\s*", text)
    if not m:
        raise ProfileError(
            f"start: can't read {text!r}; write a season or month, e.g. `summer 2027`"
        )
    word, year = m.group(1).lower(), m.group(2)
    word = SEASON_ALIASES.get(word, word)
    if word in SEASONS:
        fi_season, months = SEASONS[word]
        parts = [_dated(rf"{word}|{fi_season}\w*", year)]
        parts += [_month_pattern(n, year) for n in months]
        return "|".join(parts)
    for number, (en, fi) in enumerate(MONTHS, 1):
        if word in (en, en[:3], en[:4]) or word.startswith(f"{fi}kuu"):
            return _month_pattern(number, year)
    raise ProfileError(
        f"start: {m.group(1)!r} isn't a season or month; e.g. `summer 2027`, `June 2027`"
    )


def _month_pattern(number: int, year: str | None) -> str:
    en, fi = MONTHS[number - 1]
    return _dated(rf"{en[:3]}(?:{en[3:]})?\.?|{fi}kuu\w*", year)


def _dated(word: str, year: str | None) -> str:
    """`word` as a whole word, followed by `year` when one is given."""
    tail = rf"(?:\s+(?:of\s+)?{year})" if year else ""
    return rf"\b(?:{word}){tail}\b"


def _words(value: Any, where: str) -> list[str]:
    """A list of words, or one word / comma-separated words as a string."""
    if value is None:
        return []
    if isinstance(value, str):
        value = value.split(",")
    if not isinstance(value, list) or not all(isinstance(w, str) for w in value):
        raise ProfileError(f"{where} must be a list of words, e.g. [Helsinki, Espoo]")
    return [w.strip() for w in value if w.strip()]
