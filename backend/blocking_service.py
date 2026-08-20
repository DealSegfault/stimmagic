"""Deterministic top-down blocking views derived from canonical shot rows.

The generator deliberately stays conservative: it turns explicit screenplay
language into a reviewable draft and never presents inferred staging as an
approved director decision. Approved payloads can be persisted in
``ProjectShot.settings.blocking`` by the Production UI.
"""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from typing import Any


VIEW_WIDTH = 900
VIEW_HEIGHT = 600
PIXELS_PER_METER = 82.0

SPACES = [
    {
        "id": "kitchen",
        "label": "Cuisine ouverte",
        "x": 55,
        "y": 55,
        "width": 285,
        "height": 230,
    },
    {"id": "living", "label": "Salon", "x": 340, "y": 55, "width": 390, "height": 345},
    {
        "id": "hallway",
        "label": "Couloir intérieur",
        "x": 340,
        "y": 400,
        "width": 390,
        "height": 145,
    },
    {"id": "entry", "label": "Entrée", "x": 625, "y": 260, "width": 105, "height": 140},
    {
        "id": "exterior",
        "label": "Couloir extérieur",
        "x": 760,
        "y": 245,
        "width": 115,
        "height": 170,
    },
]

POSITIONS = {
    "kitchen": (215.0, 175.0),
    "worktop": (145.0, 130.0),
    "living": (455.0, 230.0),
    "coffee_table": (535.0, 265.0),
    "windows": (500.0, 82.0),
    "inside_door": (675.0, 330.0),
    "peephole": (705.0, 330.0),
    "exterior_door": (800.0, 330.0),
    "hallway": (535.0, 470.0),
    "office": (405.0, 485.0),
    "bathroom": (670.0, 485.0),
    "black": (450.0, 300.0),
}

POSITION_LABELS = {
    "kitchen": "centre cuisine",
    "worktop": "plan de travail",
    "living": "centre salon",
    "coffee_table": "table basse",
    "windows": "grandes fenêtres",
    "inside_door": "seuil intérieur",
    "peephole": "judas",
    "exterior_door": "seuil extérieur",
    "hallway": "couloir intérieur",
    "office": "entrée du bureau",
    "bathroom": "porte de la salle de bain",
    "black": "hors espace visible",
}

PROP_SPECS = (
    ("phone", "Téléphone", "Tél", "coffee_table", ("telephone", "portable")),
    ("cup", "Tasse", "Tas", "worktop", ("tasse", "the")),
    ("kettle", "Bouilloire", "Bou", "worktop", ("bouilloire",)),
    ("knife", "Couteau", "Cou", "worktop", ("couteau",)),
    ("chair", "Chaise", "Cha", "kitchen", ("chaise",)),
    ("footprints", "Empreintes", "Emp", "hallway", ("empreinte", "traces mouillees")),
    ("door", "Porte d’entrée", "Por", "peephole", ("porte", "judas")),
)

MOVEMENT_TERMS = (
    "avance",
    "traverse",
    "entre",
    "recule",
    "se retourne",
    "tourne",
    "s approche",
    "marche",
    "va dans",
    "rejoint",
    "ouvre les rideaux",
    "retire son visage",
)


def _normalized(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value or "")
    return "".join(
        char for char in decomposed if not unicodedata.combining(char)
    ).lower()


def _has(text: str, *terms: str) -> bool:
    return any(term in text for term in terms)


def _source_hash(description: str, duration: float) -> str:
    payload = f"{description.strip()}|{duration:.3f}".encode()
    return hashlib.sha1(payload).hexdigest()[:16]


def _distance_meters(first: tuple[float, float], second: tuple[float, float]) -> float:
    return round(math.dist(first, second) / PIXELS_PER_METER, 1)


def _angle_to(first: tuple[float, float], second: tuple[float, float]) -> float:
    return round(
        math.degrees(math.atan2(second[1] - first[1], second[0] - first[0])), 1
    )


def _position_name(point: tuple[float, float]) -> str:
    nearest = min(POSITIONS, key=lambda key: math.dist(point, POSITIONS[key]))
    return POSITION_LABELS[nearest]


def _space_for_point(point: tuple[float, float]) -> str:
    x, y = point
    if x >= 745:
        return "exterior"
    if y >= 395:
        return "hallway"
    if x <= 340:
        return "kitchen"
    if x >= 620 and 240 <= y <= 410:
        return "entry"
    return "living"


def _without_dialogue(value: str) -> str:
    value = re.sub(r"«[^»]*»|\"[^\"]*\"", " ", value)
    value = re.sub(
        r"\b(?:VOIX|T[EÉ]L[EÉ]PHONE|MAYA(?:\s+EXT[EÉ]RIEURE)?)\s*:\s*",
        " ",
        value,
        flags=re.I,
    )
    return re.sub(r"\s+", " ", value).strip()


def _infer_target(text: str, fallback: str) -> str:
    if _has(text, "salle de bain"):
        return "bathroom"
    if _has(text, "bureau"):
        return "office"
    if _has(text, "couloir sombre", "couloir donnant"):
        return "hallway"
    if _has(text, "judas"):
        return "peephole"
    if _has(text, "porte", "poignee", "seuil"):
        return "inside_door"
    if _has(text, "rideau", "fenetre"):
        return "windows"
    if _has(text, "telephone", "table basse"):
        return "coffee_table"
    if _has(text, "bouilloire", "tasse", "tiroir", "couteau", "plan de travail"):
        return "worktop"
    if _has(text, "cuisine"):
        return "kitchen"
    if _has(text, "salon", "appartement"):
        return "living"
    return fallback


def _infer_location(text: str, previous: str | None) -> tuple[str, str]:
    if _has(text, "cut brutal au noir", "noir. silence total"):
        return "black", "Noir / espace suspendu"
    if _has(text, "couloir exterieur", "exterieur."):
        return "exterior", "Couloir extérieur"
    if _has(text, "salle de bain"):
        return "hallway", "Couloir vers salle de bain"
    if _has(text, "bureau", "couloir sombre"):
        return "hallway", "Couloir intérieur"
    if _has(text, "porte", "judas", "poignee"):
        return "entry", "Entrée / porte palière"
    if _has(text, "interieur.", "retour interieur"):
        return "entry", "Entrée / porte palière"
    if _has(
        text,
        "cuisine",
        "bouilloire",
        "tasse",
        "tiroir",
        "chaise",
        "couteau",
        "plan de travail",
    ):
        return "kitchen", "Cuisine ouverte"
    if _has(text, "fenetre", "rideau", "salon", "table basse"):
        return "living", "Salon"
    if previous and previous != "black":
        labels = {space["id"]: space["label"] for space in SPACES}
        return previous, labels.get(previous, "Appartement")
    return "living", "Appartement"


def _shot_profile(text: str) -> tuple[str, str, str]:
    if _has(text, "cut brutal au noir"):
        return "BLACK", "—", "Cut sec"
    if _has(text, "pov"):
        return "POV", "35 mm", "Point de vue subjectif"
    if _has(text, "insert", "gp ", "gros plan", "close"):
        lens = (
            "85 mm"
            if not _has(text, "main", "doigt", "tasse", "telephone", "tiroir", "sol")
            else "50 mm macro"
        )
        return (
            ("ECU" if _has(text, "gp ", "insert") else "CU"),
            lens,
            "Fixe, focus verrouillé",
        )
    if _has(text, "plan large", "grand plan", "plan d ensemble", "large appartement"):
        return "WS", "35 mm", "Handheld respiré, amplitude faible"
    if _has(text, "medium", "moyen"):
        return "MS", "50 mm", "Handheld respiré"
    return "MS", "50 mm", "Handheld respiré"


def _camera_emotion(text: str, default: str) -> str:
    if _has(text, "se fige", "fige", "comprend", "revelation"):
        return "Fixe 0,5 s puis push-in très lent, course ≤ 15 cm"
    if _has(
        text, "brutal", "terrif", "tension", "livide", "panique", "plus forte", "crie"
    ):
        return "Handheld nerveux, micro-dérives irrégulières, sans stabilisateur"
    if _has(text, "lent travelling", "tres lent recul", "lent recul"):
        return "Travelling physique très lent, sans zoom"
    if _has(text, "quasi statique", "aucun recul"):
        return "Quasi statique, respiration caméra minimale"
    if _has(text, "silence", "attend", "calme"):
        return "Handheld fluide, respiration régulière et retenue"
    return default


def _camera_for(
    target: tuple[float, float], plan_type: str, movement: str
) -> dict[str, Any]:
    distance = {"ECU": 72.0, "CU": 105.0, "MS": 150.0, "WS": 230.0, "POV": 30.0}.get(
        plan_type, 150.0
    )
    x = max(35.0, min(VIEW_WIDTH - 35.0, target[0] - distance))
    y = max(
        35.0, min(VIEW_HEIGHT - 35.0, target[1] + (35.0 if plan_type != "WS" else 80.0))
    )
    return {
        "x": round(x, 1),
        "y": round(y, 1),
        "facing": _angle_to((x, y), target),
        "movement": movement,
        "fov": 32 if plan_type in {"ECU", "CU"} else 48,
        "target_x": round(target[0], 1),
        "target_y": round(target[1], 1),
        "distance_meters": _distance_meters((x, y), target),
    }


def _visible_actors(
    spatial_text: str, full_text: str, location_id: str
) -> list[tuple[str, str, str]]:
    two_mayas = _has(
        spatial_text,
        "deux maya",
        "face a face",
        "maya la retient",
        "maya referme la porte",
    )
    third_maya = _has(spatial_text, "troisieme maya")
    exterior_subject = _has(spatial_text, "maya exterieure") and not _has(
        spatial_text, "hors champ", "identique a celle de maya exterieure"
    )
    exterior_speaker_only = (
        "maya exterieure :" in full_text and "maya" not in spatial_text
    )
    exterior_named = exterior_subject or two_mayas or exterior_speaker_only
    interior_named = (
        ("maya" in spatial_text or "maya :" in full_text)
        and not (_has(spatial_text, "pov judas") and exterior_named)
        and not _has(
            spatial_text,
            "plan de la porte vide",
            "appartement apparemment vide",
            "aucun personnage",
        )
        and (
            not exterior_subject
            or two_mayas
            or third_maya
            or _has(spatial_text, "notre maya", "maya principale")
        )
    )
    if two_mayas:
        interior_named = True
        exterior_named = True
    if location_id == "exterior" and "maya" in spatial_text:
        exterior_named = True
        interior_named = False
    actors: list[tuple[str, str, str]] = []
    if interior_named:
        actors.append(("maya", "Maya", "M"))
    if exterior_named:
        actors.append(("maya_ext", "Maya extérieure", "Mx"))
    if third_maya:
        actors.append(("maya_3", "Troisième Maya", "M3"))
    return actors


def _actor_target(actor_id: str, text: str, location_id: str, fallback: str) -> str:
    if actor_id == "maya_3":
        return "office"
    if actor_id == "maya_ext" and location_id == "exterior":
        return "exterior_door"
    target = _infer_target(text, fallback)
    if location_id == "exterior":
        return "exterior_door"
    return target


def _gaze_target(
    text: str, actor_id: str, position: tuple[float, float]
) -> tuple[float, float, str]:
    if actor_id == "maya_ext":
        point = POSITIONS["peephole"]
        return point[0], point[1], "judas / Maya intérieure"
    if _has(text, "main", "paume", "cicatrice"):
        return position[0] + 18.0, position[1] + 12.0, "sa main"
    if _has(text, "telephone", "ecran", "numero"):
        point = POSITIONS["coffee_table"]
        return point[0], point[1], "téléphone"
    if _has(text, "porte", "judas", "poignee"):
        point = POSITIONS["peephole"]
        return point[0], point[1], "porte / judas"
    if _has(text, "cuisine", "tasse", "couteau", "tiroir"):
        point = POSITIONS["worktop"]
        return point[0], point[1], "plan de travail"
    if _has(text, "fenetre", "rideau"):
        point = POSITIONS["windows"]
        return point[0], point[1], "fenêtres"
    if _has(text, "sol", "empreinte", "regard descend"):
        return position[0] + 12.0, position[1] + 20.0, "sol"
    return position[0] + 65.0, position[1], "axe du plan"


def _action_beats(description: str) -> list[str]:
    without_dialogue = re.sub(r"«[^»]*»|\"[^\"]*\"", " ", description)
    clauses = re.split(r"(?<=[.!?])\s+|\s*;\s*", without_dialogue)
    beats: list[str] = []
    for clause in clauses:
        cleaned = re.sub(
            r"\b(?:MAYA(?: EXT[EÉ]RIEURE)?|VOIX|T[EÉ]L[EÉ]PHONE)\s*:\s*",
            "",
            clause,
            flags=re.I,
        )
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" .:—-")
        if len(cleaned) >= 4 and cleaned.lower() not in {
            "silence",
            "intérieur",
            "extérieur",
        }:
            beats.append(cleaned[0].upper() + cleaned[1:])
    normalized = _normalized(description)
    micro_beats: list[str] = []
    if _has(normalized, "se fige", "fige"):
        micro_beats.append("Corps figé 0,5 s; regard verrouillé; inspiration retardée")
    if _has(normalized, "hesite"):
        micro_beats.append(
            "Poids retenu sur l’appui arrière; main suspendue avant l’action"
        )
    if _has(normalized, "se retourne", "tourne la tete", "regard descend"):
        micro_beats.append(
            "Le regard part d’abord; tête puis épaules suivent avec un léger décalage"
        )
    if _has(normalized, "livide", "terrif", "essouffl", "respiration rapide"):
        micro_beats.append(
            "Respiration courte visible dans les épaules; appuis instables mais contenus"
        )
    if _has(normalized, "silence"):
        micro_beats.append(
            "Tenir le regard et la position pendant le silence; aucun geste parasite"
        )
    return beats + micro_beats or [
        "Tenir la position et l’axe de regard établis par le raccord"
    ]


def _performance_beats(description: str) -> list[str]:
    """Translate broad screenplay emotions into observable actor direction."""
    text = _normalized(description)
    beats: list[str] = []
    if _has(text, "se fige", "fige", "choc", "stupef"):
        beats.append(
            "Corps immobile 0,3–0,5 s; pupilles dilatées, lèvres entrouvertes, puis une inspiration nasale retardée."
        )
    if _has(
        text, "angoiss", "nerveu", "panique", "inquiet", "terrifi", "respiration rapide"
    ):
        beats.append(
            "Inspiration nasale courte; déglutition visible; lèvre inférieure légèrement rentrée; regard verrouillé sur la menace."
        )
    if _has(text, "triste", "vulner", "livide", "desespoir"):
        beats.append(
            "Sourcils resserrés au centre; tête légèrement abaissée; lèvres instables; yeux humides mais sans larme qui coule."
        )
    if _has(text, "colere", "rage", "furieu", "determin"):
        beats.append(
            "Masséter tendu sous la peau; narines ouvertes sur l’accent; regard fixe sans clignement au point culminant."
        )
    if _has(text, "hesite", "retient", "reprime", "contient"):
        beats.append(
            "Mâchoire qui tremble une fois puis se resserre; déglutition tardive; inspiration lente visible dans la poitrine."
        )
    if _has(text, "calme", "controle", "sourit"):
        beats.append(
            "Respiration régulière; bras relâchés; clignement lent; le sourire se construit progressivement au lieu d’apparaître d’un coup."
        )
    if _has(text, "surpris", "n'en revient pas", "incredule"):
        beats.append(
            "Clignement lent; tête inclinée de 5–10°; lèvres pressées; un seul sourcil se soulève, regard maintenu sur la source."
        )
    if _has(text, "silence", "attend", "immobile"):
        beats.append(
            "Respiration basse et visible; regard tenu dans une direction précise; aucune gesticulation de remplissage."
        )
    return beats or [
        "Respiration naturelle visible; regard orienté vers la cible indiquée; micro-ajustement d’appui sans geste parasite."
    ]


def _props_for(text: str) -> list[dict[str, Any]]:
    props: list[dict[str, Any]] = []
    for prop_id, label, symbol, position_key, terms in PROP_SPECS:
        if not _has(text, *terms):
            continue
        x, y = POSITIONS[position_key]
        if prop_id == "knife" and _has(text, "range"):
            x -= 36.0
        if prop_id == "chair" and _has(text, "sortie"):
            y += 42.0
        props.append({"id": prop_id, "label": label, "symbol": symbol, "x": x, "y": y})
    return props


def _persisted_blocking(
    settings: dict[str, Any], source_hash: str
) -> dict[str, Any] | None:
    blocking = settings.get("blocking")
    if (
        not isinstance(blocking, dict)
        or blocking.get("version") != 1
        or not blocking.get("frames")
    ):
        return None
    if blocking.get("source_hash") != source_hash:
        return None
    return blocking


def _restore_state_from_view(state: dict[str, Any], view: dict[str, Any]) -> None:
    frames = view.get("frames") or []
    if frames:
        for actor in frames[-1].get("actors") or []:
            state.setdefault("last_actor_positions", {})[actor["id"]] = (
                float(actor["x"]),
                float(actor["y"]),
            )
    state["previous_view"] = view
    state["previous_location"] = (view.get("location") or {}).get("id")


def build_blocking_view(
    shot: Any,
    scene: Any,
    state: dict[str, Any] | None = None,
    *,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one one-second-granularity blocking view and advance ``state``."""
    state = state if state is not None else {}
    description = str(
        getattr(shot, "description", "") or getattr(shot, "prompt", "") or ""
    )
    shot_title = str(getattr(shot, "title", "") or "")
    duration = max(0.5, float(getattr(shot, "duration", 4.0) or 4.0))
    source_hash = _source_hash(f"{shot_title}|{description}", duration)
    persisted = _persisted_blocking(settings or {}, source_hash)
    if persisted is not None:
        _restore_state_from_view(state, persisted)
        return persisted

    full_text = _normalized(f"{shot_title}. {description}")
    text = _normalized(_without_dialogue(f"{shot_title}. {description}"))
    location_text = _normalized(_without_dialogue(description))
    previous_view = state.get("previous_view")
    previous_location = state.get("previous_location")
    last_positions: dict[str, tuple[float, float]] = state.setdefault(
        "last_actor_positions", {}
    )
    location_id, location_label = _infer_location(location_text, previous_location)
    explicit_location = _has(
        location_text,
        "cuisine",
        "bouilloire",
        "tasse",
        "tiroir",
        "chaise",
        "couteau",
        "plan de travail",
        "fenetre",
        "rideau",
        "salon",
        "table basse",
        "porte",
        "judas",
        "poignee",
        "couloir",
        "bureau",
        "salle de bain",
        "exterieur.",
        "cut brutal au noir",
    )
    if not explicit_location:
        actor_position = None
        if _has(text, "maya exterieure") and not _has(
            text, "notre maya", "identique a celle de maya exterieure"
        ):
            actor_position = last_positions.get("maya_ext")
        elif "maya" in full_text:
            actor_position = last_positions.get("maya")
        if actor_position is not None:
            location_id = _space_for_point(actor_position)
            location_label = next(
                (space["label"] for space in SPACES if space["id"] == location_id),
                "Appartement",
            )
    plan_type, lens, default_movement = _shot_profile(text)
    movement = _camera_emotion(text, default_movement)
    fallback_target = {
        "kitchen": "kitchen",
        "living": "living",
        "entry": "inside_door",
        "hallway": "hallway",
        "exterior": "exterior_door",
        "black": "black",
    }.get(location_id, "living")
    target_key = _infer_target(text, fallback_target)
    camera = _camera_for(POSITIONS[target_key], plan_type, movement)
    camera.update({"lens": lens, "plan_type": plan_type})

    moving = _has(text, *MOVEMENT_TERMS)
    actors_spec: list[dict[str, Any]] = []
    visible_actors = _visible_actors(text, full_text, location_id)
    for actor_id, label, initials in visible_actors:
        target_name = _actor_target(actor_id, text, location_id, fallback_target)
        target = POSITIONS[target_name]
        if actor_id == "maya" and _has(text, "troisieme maya"):
            target = last_positions.get(actor_id, POSITIONS["living"])
            target_name = min(
                POSITIONS, key=lambda key: math.dist(target, POSITIONS[key])
            )
        if (
            actor_id == "maya"
            and any(item[0] == "maya_ext" for item in visible_actors)
            and target_name == "inside_door"
        ):
            target = (645.0, 330.0)
        if actor_id == "maya_ext" and target_name == "inside_door":
            target = (715.0, 330.0)
        default_start = POSITIONS["exterior_door"] if actor_id == "maya_ext" else target
        start = last_positions.get(actor_id, default_start)
        if _has(text, "nouvel angle", "deja", "retour") and not moving:
            start = target
        end = (
            target
            if moving
            or actor_id not in last_positions
            or _has(text, "deja", "face a face")
            else start
        )
        if _has(text, "cut avant son arrivee"):
            end = (target[0] - 55.0, target[1] + 18.0)
        if _has(text, "recule", "retire brutalement") and actor_id == "maya":
            end = (max(80.0, start[0] - 85.0), min(540.0, start[1] + 24.0))
        gaze_x, gaze_y, gaze_label = _gaze_target(text, actor_id, end)
        actors_spec.append(
            {
                "id": actor_id,
                "label": label,
                "initials": initials,
                "start": start,
                "end": end,
                "target_label": POSITION_LABELS[target_name],
                "gaze_x": gaze_x,
                "gaze_y": gaze_y,
                "gaze_label": gaze_label,
            }
        )

    beats = _action_beats(description)
    performance_beats = _performance_beats(description)
    frame_count = max(1, int(math.ceil(duration)))
    frames: list[dict[str, Any]] = []
    for second in range(frame_count):
        time_start = float(second)
        time_end = min(duration, float(second + 1))
        midpoint = min(1.0, ((time_start + time_end) / 2.0) / duration)
        previous_midpoint = min(1.0, time_start / duration)
        frame_actors: list[dict[str, Any]] = []
        movement_phrases: list[str] = []
        for actor in actors_spec:
            sx, sy = actor["start"]
            ex, ey = actor["end"]
            x = sx + (ex - sx) * midpoint
            y = sy + (ey - sy) * midpoint
            prior_x = sx + (ex - sx) * previous_midpoint
            prior_y = sy + (ey - sy) * previous_midpoint
            moved = _distance_meters((prior_x, prior_y), (x, y))
            facing = _angle_to((x, y), (actor["gaze_x"], actor["gaze_y"]))
            action = (
                f"avance d’environ {moved:.1f} m vers {actor['target_label']}"
                if moved > 0.05
                else f"tient sa position à {_position_name((x, y))}"
            )
            movement_phrases.append(f"{actor['label']} {action}")
            frame_actors.append(
                {
                    "id": actor["id"],
                    "label": actor["label"],
                    "initials": actor["initials"],
                    "x": round(x, 1),
                    "y": round(y, 1),
                    "facing": facing,
                    "gaze_x": round(actor["gaze_x"], 1),
                    "gaze_y": round(actor["gaze_y"], 1),
                    "gaze_label": actor["gaze_label"],
                    "position_label": _position_name((x, y)),
                    "action": action,
                }
            )
        beat_index = min(len(beats) - 1, int(second * len(beats) / frame_count))
        beat = beats[beat_index]
        performance_index = min(
            len(performance_beats) - 1,
            int(second * len(performance_beats) / frame_count),
        )
        performance_note = performance_beats[performance_index]
        relationships = []
        for actor_index, actor in enumerate(frame_actors):
            for other in frame_actors[actor_index + 1 :]:
                relationships.append(
                    {
                        "from": actor["label"],
                        "to": other["label"],
                        "distance_meters": _distance_meters(
                            (float(actor["x"]), float(actor["y"])),
                            (float(other["x"]), float(other["y"])),
                        ),
                    }
                )
        spatial_summary = (
            "; ".join(movement_phrases)
            if movement_phrases
            else f"Aucun personnage visible; axe maintenu sur {POSITION_LABELS[target_key]}"
        )
        if relationships:
            spatial_summary += "; " + "; ".join(
                f"{relationship['from']} ↔ {relationship['to']} : "
                f"{relationship['distance_meters']:.1f} m"
                for relationship in relationships
            )
        if len(frame_actors) > 1:
            performance_note += " Réactions décalées de 0,3–0,5 s entre partenaires; jamais parfaitement synchrones."
        frames.append(
            {
                "index": second,
                "time_start": round(time_start, 1),
                "time_end": round(time_end, 1),
                "summary": beat,
                "spatial_note": spatial_summary + ".",
                "camera_note": f"{lens} · {movement}",
                "performance_note": performance_note,
                "actors": frame_actors,
                "relationships": relationships,
            }
        )

    previous_actor_positions: dict[str, tuple[float, float]] = {}
    if previous_view and previous_view.get("frames"):
        previous_actor_positions = {
            actor["id"]: (float(actor["x"]), float(actor["y"]))
            for actor in previous_view["frames"][-1].get("actors", [])
        }
    jumps = []
    for actor in actors_spec:
        if actor["id"] not in last_positions:
            continue
        distance = _distance_meters(last_positions[actor["id"]], actor["start"])
        if distance > 1.2:
            jumps.append({"actor": actor["label"], "distance_meters": distance})
    explicit_bridge = _has(
        text, "nouvel angle", "deja", "retour", "pov", "cut", "exterieur"
    )
    if jumps:
        verdict = "review"
        message = (
            "Ellipse spatiale écrite dans le plan; valider la distance du raccord."
            if explicit_bridge
            else "Saut spatial non motivé dans le texte; vérifier le raccord de position."
        )
    elif previous_view and not actors_spec:
        verdict = "cutaway"
        message = "Plan de coupe: conserver la dernière position connue pour le retour personnage."
    elif previous_view:
        verdict = "ok"
        message = "Raccord spatial lisible à partir de la dernière position connue."
    else:
        verdict = "start"
        message = "Premier plan: positions de référence à valider."

    for actor in actors_spec:
        last_positions[actor["id"]] = actor["end"]

    view = {
        "version": 1,
        "status": "draft",
        "source": "script-inference",
        "source_hash": source_hash,
        "shot_id": int(getattr(shot, "id", 0) or 0),
        "scene_id": int(getattr(scene, "id", 0) or 0),
        "duration": duration,
        "location": {
            "id": location_id,
            "label": location_label,
            "main_axis": "Ouest → est · cuisine vers porte palière",
            "main_view": "Nord en haut · vue zénithale",
        },
        "spaces": SPACES,
        "camera": camera,
        "props": _props_for(text),
        "frames": frames,
        "continuity": {
            "previous_shot_id": previous_view.get("shot_id") if previous_view else None,
            "verdict": verdict,
            "message": message,
            "jumps": jumps,
            "previous_actor_positions": [
                {"id": actor_id, "x": point[0], "y": point[1]}
                for actor_id, point in previous_actor_positions.items()
            ],
        },
    }
    state["previous_view"] = view
    state["previous_location"] = location_id
    return view
