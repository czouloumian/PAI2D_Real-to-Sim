import base64
import re
import requests
from collections import defaultdict
from promptToJson_auxilieres import validate_json_response, object_rec
from sceneBuilding import initPosAndQuat, processRelations, processOrientations

SCENE_WIDTH = 5.0   # les limitations de la scene pour les positions normalisées, on peut changer
SCENE_DEPTH = 5.0  

# Z est difficile a gerer pour les objets qui sont sur d'autre objet donc ces trois relations selont gerer par processRelations
# les autres (left_of, right_of…) sont gerees par les positions x y norm de l'image
VERTICAL_RELATIONS = {"on", "under", "inside"}
RE_SUFFIX = re.compile(r'_\d+$')   

def load_images(image_sources):
    images = []
    for source in image_sources:
        with open(str(source), "rb") as f:
            images.append(base64.b64encode(f.read()).decode("utf-8"))
    return images

def call_vision_llm(images_b64, system_prompt, user_prompt):
    payload = {
        "model": "llama3.2-vision",
        "system": system_prompt,
        "prompt": user_prompt,
        "images": images_b64,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0}
    }
    return validate_json_response(payload)


# ─────────────────────────────────────────────────────────────────────────────
# ÉTAPE 1 — DÉTECTION VISUELLE + ESTIMATIONS + RELATIONS
# ─────────────────────────────────────────────────────────────────────────────

VALID_ORIENTATIONS = { "default", "turn_left", "turn_right", "turn_around","tip_forward", "tip_backward", "tip_left", "tip_right", "upside_down"}

def detect_and_estimate(images_b64):
    """
    Le LLM vision analyse les images et retourne :
      - objects  : liste de {label, pos_norm, scale, orientation}
      - relations: liste de {type, subject, object}

    Objectif : maximiser la ressemblance avec l'image d'origine.
    """
    system_prompt = """You are a strict JSON API. Your goal is to reconstruct a 3D scene \
that matches the image(s) as closely as possible.

TASK:
1. Detect every distinct visible object in the image(s).
2. For each object estimate:
   - pos_norm: [x, y] — normalised centre of the object in the image.
       x = 0.0 → left edge,  x = 1.0 → right edge.
       y = 0.0 → top edge,   y = 1.0 → bottom edge.
       Be as precise as possible: use the actual centre of the object's bounding box.
   - scale: factor to reach the object's real-world size.
       Estimate from the apparent size relative to other objects and the scene.
       Real-world size references:
         washing machine  ~0.60 × 0.60 × 0.85 m  |  fridge   ~0.70 × 0.70 × 1.80 m
         trash bin        ~0.35 × 0.35 × 0.55 m  |  oven     ~0.60 × 0.60 × 0.60 m
         toaster          ~0.30 × 0.20 × 0.20 m  |  laptop   ~0.35 × 0.25 × 0.02 m
         banana           ~0.18 × 0.04 × 0.04 m  |  mug      ~0.08 × 0.08 × 0.10 m
   - orientation: choose ONE value that best describes the visible rotation:
       "default"      — normal upright, no visible rotation
       "turn_left"    — rotated 90° left around the vertical axis (seen from above)
       "turn_right"   — rotated 90° right around the vertical axis (seen from above)
       "turn_around"  — rotated 180° around vertical axis (facing opposite direction)
       "tip_forward"  — tilted/fallen forward toward the camera
       "tip_backward" — tilted/fallen backward away from the camera
       "tip_left"     — tilted/fallen to the left
       "tip_right"    — tilted/fallen to the right
       "upside_down"  — completely inverted
       → Use "default" unless a rotation is CLEARLY visible.
3. Extract ONLY the spatial relations that are unambiguously visible:
   - "on"         : A rests on top of B      - "under"      : A is below B
   - "inside"     : A is inside B            - "left_of"    : A is to the left of B
   - "right_of"   : A is to the right of B   - "in_front_of": A is closer to camera than B
   - "behind"     : A is further from camera - "against"    : A is pressed flat against B

OUTPUT FORMAT — return ONLY this JSON:
{
  "objects": [
    {
      "label": "<nom en français>",
      "pos_norm": [<x 0.0-1.0>, <y 0.0-1.0>],
      "scale": <float>,
      "orientation": "<value from the list above>"
    }
  ],
  "relations": [
    {"type": "<relation>", "subject": "<label_A>", "object": "<label_B>"}
  ]
}

RULES:
- One entry per distinct instance (two bananas = two entries with different pos_norm).
- Simple French labels: "frigo", "lave-linge", "poubelle", "banane", "mug", etc.
- subject/object in relations must be EXACT labels from the objects list above.
- "relations": [] if nothing is clearly visible.
- Multiple images = same scene from different angles — combine them.
- Raw JSON only, no markdown, no comments."""

    for attempt in range(3):
        result = call_vision_llm(images_b64, system_prompt,"Analyse the image(s) as precisely as possible and return the JSON.")
        if result.get("objects"):
            return result
        print(f"[detect_and_estimate] retry {attempt + 1} — aucun objet retourne")

    return {"objects": [], "relations": []}


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def find_root(catalogue_labels, remapped_relations):
    """
    Racine = objet qui ne repose sur rien (absent de 'subject' dans les relations verticales)
    Fallback sur le premier label
    """
    supported = {r["subject"] for r in remapped_relations if r["type"] in VERTICAL_RELATIONS}
    for label in catalogue_labels:
        if label not in supported:
            return label
    return next(iter(catalogue_labels))


def remap_relations(relations, label_mapping, valid_labels):
    """
    traduit les labels vision -> labels catalogue dans les relations, et filtre celles dont les deux extremites ne sont pas dans le catalogue.
    """
    remapped = []
    for rel in relations:
        subj = label_mapping.get(rel["subject"], rel["subject"])
        obj  = label_mapping.get(rel["object"],  rel["object"])
        if subj in valid_labels and obj in valid_labels:
            remapped.append({"type": rel["type"], "subject": subj, "object": obj})
    return remapped


# ─────────────────────────────────────────────────────────────────────────────
# FONCTION PRINCIPALE
# ─────────────────────────────────────────────────────────────────────────────

def scene_from_image(image_paths):
    """
    Génère une scène 3D à partir d'images.

    Pipeline :
      1. Vision LLM  -> objects (label, pos_norm, scale, quat) + relations
      2. object_rec  -> mapping labels → catalogue
      3. initPosAndQuat + processRelations (sceneBuilding) -> z
      4. Override x,y avec les positions derivee de l'image (pos_norm)

    Retourne : Liste de dicts au format V2 : [{"id", "urdf", "path", "scale", "quat", "pos"}, etc]
    """
    images = load_images(image_paths)

    # detecte + estimation visuelle
    detected_raw = detect_and_estimate(images)
    detected_objects  = detected_raw.get("objects", [])
    detected_relations = detected_raw.get("relations", [])

    if not detected_objects:
        print("[scene_from_image] Aucun objet détecté.")
        return []

    # mapping
    labels_prompt = ", ".join(o["label"] for o in detected_objects)
    print(f"[mapping_scene_from_image] Objets detectes : {labels_prompt}")

    objet_reconnus, non_reconnus = object_rec(labels_prompt)
    if non_reconnus:
        print(f"[scene_from_image] Non reconnus dans le catalogue : {non_reconnus}")
    if not objet_reconnus:
        return []

    valid_labels = set(objet_reconnus.keys())

    # Construire label_mapping vision -> catalogue et pool d'estimations
    estimates_pool = defaultdict(list)
    for obj in detected_objects:
        estimates_pool[obj["label"]].append(obj)

    label_mapping  = {}   # vision_label -> catalogue_label
    item_estimates = {}   # catalogue_label -> estimation visuelle
    for cat_label, info in objet_reconnus.items():
        base = RE_SUFFIX.sub('', cat_label)
        pool = estimates_pool.get(cat_label) or estimates_pool.get(base) or []
        est  = pool.pop(0) if pool else {} 
        vision_label = est.get("label", base)
        label_mapping[vision_label] = cat_label
        item_estimates[cat_label]   = est

    # remap des relations et identification de la racine
    all_relations      = remap_relations(detected_relations, label_mapping, valid_labels)
    vertical_relations = [r for r in all_relations if r["type"] in VERTICAL_RELATIONS]
    root_id            = find_root(list(objet_reconnus.keys()), vertical_relations)

    items = [
        {
            "id":         cat_label,
            "urdf":       info["urdf"],
            "path":       info["path"],
            "dimensions": info.get("dimensions") or [1.0, 1.0, 1.0],
            "scale":      item_estimates.get(cat_label, {}).get("scale", 1.0),
            "root":       "true" if cat_label == root_id else "false",
        }
        for cat_label, info in objet_reconnus.items()
    ]

    # processOrientations met à jour quat et dimensions
    # Doit tourner AVANT initPosAndQuat pour que le z initial soit calcule
    orientations = [
        {"id": cat_label, "turn": item_estimates[cat_label].get("orientation", "default")}
        for cat_label in objet_reconnus
        if item_estimates.get(cat_label, {}).get("orientation", "default") != "default"
           and item_estimates.get(cat_label, {}).get("orientation") in VALID_ORIENTATIONS
    ]
    items = processOrientations(items, orientations)

    # z via sceneBuilding — juste les relations verticales (on/under/inside)
    items = initPosAndQuat(items)
    items = processRelations(items, vertical_relations)

    # Override x,y avec les positions image
    for item in items:
        pos_norm = item_estimates.get(item["id"], {}).get("pos_norm", [0.5, 0.5])
        _, _, z  = item["pos"]
        item["pos"] = [
            round((pos_norm[0] - 0.5) * SCENE_WIDTH, 3),
            round((1.0 - pos_norm[1]) * SCENE_DEPTH, 3),
            z,
        ]

    return items
