import base64
import requests
import json
from promptToJson_auxilieres import (
    _objects_desc, validate_json_response,
    URL, object_rec
)

# ─────────────────────────────────────────────
#  Utilitaires vision
# ─────────────────────────────────────────────

def encode_image(path_to_image):
    """Encode l'image en base64 pour l'API Ollama vision."""
    with open(path_to_image, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def call_vision(prompt, image_b64, system=None):
    """Appel brut à llama3.2-vision — retourne la réponse texte brute.
    On demande volontairement du texte libre (pas de JSON) car le VLM
    est beaucoup plus fiable sur des descriptions que sur du JSON strict.
    """
    payload = {
        "model": "llama3.2-vision",
        "prompt": prompt,
        "images": [image_b64],
        "stream": False,
        "options": {"temperature": 0}
    }
    if system:
        payload["system"] = system

    try:
        response = requests.post(URL, json=payload, timeout=300)
    except requests.exceptions.ConnectionError:
        raise ConnectionError("Impossible de joindre Ollama.")

    if response.status_code != 200:
        raise RuntimeError(f"Erreur Ollama vision (HTTP {response.status_code}): {response.text}")

    return response.json().get("response", "")


# ─────────────────────────────────────────────
#  ÉTAPE 1a — Détection des objets (VLM, texte libre)
# ─────────────────────────────────────────────

def detect_objects_in_image(path_to_image):
    """Utilise llama3.2-vision pour lister les objets visibles dans l'image.

    On sépare volontairement la détection de la description spatiale :
    deux tâches simples sont plus fiables qu'une tâche complexe.

    Retourne : str — liste brute des objets, un par ligne
    """
    image_b64 = encode_image(path_to_image)
    system = (
        "You identify physical objects in images. "
        "Be factual. List only what you can clearly see."
    )
    prompt = (
        "List every distinct physical object you can see in this image. "
        "Write one object name per line, in French. "
        "Do not add descriptions, quantities, or adjectives — just the object name."
    )
    result = call_vision(prompt, image_b64, system)
    print(f"[vision] Détection objets :\n{result}")
    return result


# ─────────────────────────────────────────────
#  ÉTAPE 1b — Description spatiale (VLM, texte libre)
# ─────────────────────────────────────────────

def describe_spatial_layout(path_to_image):
    """Utilise llama3.2-vision pour décrire le placement spatial des objets.

    Se concentre sur : positions relatives (gauche/droite/devant/derrière),
    superpositions (posé sur / sous), distances, tailles relatives.
    Texte libre — pas de JSON pour rester fiable.

    Retourne : str — description spatiale brute
    """
    image_b64 = encode_image(path_to_image)
    system = (
        "You describe the spatial layout of scenes precisely. "
        "Focus on relative positions, sizes, and distances between objects."
    )
    prompt = (
        "Describe precisely the spatial arrangement of the objects in this image. "
        "For each object, mention: "
        "1) where it is (left, right, center, background, foreground), "
        "2) what it is next to / on top of / in front of, "
        "3) its approximate size relative to the other objects. "
        "Answer in French, plain text, no JSON."
    )
    result = call_vision(prompt, image_b64, system)
    print(f"[vision] Layout spatial :\n{result}")
    return result


# ─────────────────────────────────────────────
#  ÉTAPE 2 — Extraction liste JSON propre (LLM texte)
# ─────────────────────────────────────────────

def extract_object_list(detection_text, prompt=None):
    """Convertit la détection image (texte) en liste JSON propre.

    Utilise llama3.1 (texte seul) — tâche JSON simple et très fiable.
    Si un prompt textuel est fourni, ses objets sont fusionnés avec
    ceux détectés sur l'image (le prompt peut ajouter des précisions
    ou des objets non visibles sur l'image).

    Retourne : list[str] — noms d'objets en français
    """
    parts = []
    if detection_text.strip():
        parts.append(f"Objets détectés sur l'image :\n{detection_text.strip()}")
    if prompt and prompt.strip():
        parts.append(f"Précisions textuelles de l'utilisateur : {prompt.strip()}")

    combined = "\n\n".join(parts)

    system_prompt = """You extract a clean, deduplicated list of physical objects from a scene description.
        Return ONLY this JSON:
        {"objects": ["objet1", "objet2", "objet3"]}
        RULES:
        - Use French names, lowercase
        - If the same object appears multiple times in the scene, include it multiple times
          (e.g. two chairs → ["chaise", "chaise"])
        - Include ONLY concrete physical objects — no adjectives, no verbs, no descriptions
        - Output raw JSON only, no markdown, no comments"""

    payload = {
        "model": "llama3.1",
        "system": system_prompt,
        "prompt": combined,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0}
    }

    result = validate_json_response(payload)
    objects = result.get("objects", [])
    print(f"[extract] Liste objets : {objects}")
    return objects


# ─────────────────────────────────────────────
#  ÉTAPE 3 — Matching catalogue URDF (réutilise object_rec)
# ─────────────────────────────────────────────

def match_to_catalogue(object_list):
    """Fait correspondre une liste de noms d'objets au catalogue URDF.

    Construit un pseudo-prompt naturel et délègue à object_rec(),
    qui gère déjà les retry et la validation sémantique.

    Retourne : (objet_reconnus dict, non_reconnus list)
    """
    if not object_list:
        return {}, []

    scene_prompt = "Je veux " + ", ".join(f"un(e) {obj}" for obj in object_list)
    print(f"[match] Pseudo-prompt : {scene_prompt}")
    return object_rec(scene_prompt)


# ─────────────────────────────────────────────
#  ÉTAPE 4 — Positionnement fidèle à l'image (LLM texte)
# ─────────────────────────────────────────────

def object_dim_quat_from_image(layout_desc, objet_reconnus):
    """Place les objets en 3D en respectant fidèlement le layout visuel de l'image.

    Contrairement à object_dim_quat de V2 (qui se base sur le prompt textuel),
    cette fonction utilise la description spatiale extraite de l'image pour
    reproduire précisément la disposition visible.

    Params :
        layout_desc   : description spatiale en texte libre (issue de describe_spatial_layout)
        objet_reconnus: dict {label: {urdf, path, dimensions}}

    Retourne : list de dicts {id, urdf, path, scale, quat, pos}
    """
    objects_info = "\n".join(
        f'- id: "{label}" | urdf: "{info["urdf"]}" | dimensions: {info["dimensions"]} m'
        for label, info in objet_reconnus.items()
    )

    system_prompt = f"""You are a strict JSON API. You replicate a real scene into a 3D simulation.
        All dimensions are in meters. The floor is at z = 0.
        Your goal is to place objects so the simulated scene MATCHES the image layout as closely as possible.

        OBJECTS TO PLACE (with their real catalogue dimensions):
        {objects_info}

        OUTPUT FORMAT — return ONLY this JSON:
        {{
          "objects": [
            {{
              "id": "<label>",
              "urdf": "<urdf>",
              "scale": <float>,
              "quat": [<w>, <x>, <y>, <z>],
              "pos": [<x>, <y>, <z>]
            }}
          ]
        }}

        PLACEMENT RULES:
        - "id" and "urdf" must be copied verbatim from the list above
        - scale: adjust so the object matches its visual size in the image (1.0 = use real catalogue dimensions)
        - pos z: set to half of (dimensions[2] * scale) so the object rests on the floor,
                 UNLESS the image shows the object elevated (e.g. on top of another object),
                 in which case pos z = height of support + half object height
        - quat: default = [1.0, 0.0, 0.0, 0.0]. Rotate only if the image clearly shows
                a non-upright orientation.
        - pos x/y: place objects to reproduce the LEFT/RIGHT and FRONT/BACK arrangement visible
                   in the image. Use the following convention:
                   x > 0 = right, x < 0 = left,  y > 0 = forward, y < 0 = backward
        - Objects must NOT overlap. Respect the spacing visible in the image.
        - Output raw JSON only, no markdown, no comments, no explanation"""

    user_prompt = (
        f"Here is the spatial layout of the scene from the image:\n\n{layout_desc}\n\n"
        "Place each object in 3D to reproduce this layout exactly."
    )

    payload = {
        "model": "llama3.1",
        "system": system_prompt,
        "prompt": user_prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0}
    }

    obj_list = validate_json_response(payload).get("objects", [])

    # Résoudre les paths
    for obj in obj_list:
        label = obj.get("id")
        if label in objet_reconnus:
            obj["path"] = objet_reconnus[label]["path"]

    print(f"[dim_quat] {len(obj_list)} objets placés")
    return obj_list


# ─────────────────────────────────────────────
#  POINT D'ENTRÉE — Reconnaissance seule
# ─────────────────────────────────────────────

def object_rec_image(path_to_image=None, prompt=None):
    """Reconnaît les objets depuis une image et/ou un prompt textuel.

    Pipeline :
      1. llama3.2-vision → liste d'objets (texte libre)
      2. llama3.1        → liste JSON propre
      3. llama3.1        → matching catalogue + validation sémantique

    Retourne : (objet_reconnus dict, non_reconnus list)
        objet_reconnus = {label: {"urdf": ..., "path": ..., "dimensions": ...}}
    """
    if not path_to_image and not prompt:
        return {}, []

    if not path_to_image:
        print("[V3] Mode texte seul → object_rec")
        return object_rec(prompt)

    # Étape 1a : détecter les objets (VLM, texte)
    detection_text = detect_objects_in_image(path_to_image)

    # Étape 2 : extraire la liste propre (LLM texte + prompt optionnel)
    object_list = extract_object_list(detection_text, prompt)

    if not object_list:
        print("[V3] Aucun objet extrait de l'image.")
        return {}, []

    # Étape 3 : matcher au catalogue
    return match_to_catalogue(object_list)


# ─────────────────────────────────────────────
#  POINT D'ENTRÉE — Pipeline complet (objets + positions)
# ─────────────────────────────────────────────

def get_scene_from_image(path_to_image=None, prompt=None):
    """Pipeline complet : reproduit fidèlement la scène visible dans l'image.

    Pipeline :
      1. llama3.2-vision → liste d'objets       (texte libre)
      2. llama3.2-vision → layout spatial        (texte libre)
      3. llama3.1        → liste JSON propre
      4. llama3.1        → matching catalogue
      5. llama3.1        → positions 3D fidèles au layout image

    Params :
        path_to_image : chemin vers l'image (optionnel si prompt fourni)
        prompt        : description textuelle complémentaire (optionnel)

    Retourne : list de dicts {id, urdf, path, scale, quat, pos}
    """
    if not path_to_image and not prompt:
        return []

    if not path_to_image:
        # Fallback texte pur : reconnaissance + positionnement sans image
        from promptToJson_V2_LLM import object_dim_quat
        objet_reconnus, _ = object_rec(prompt)
        return object_dim_quat(prompt, objet_reconnus)

    # Étape 1a : détecter les objets
    detection_text = detect_objects_in_image(path_to_image)

    # Étape 1b : décrire le layout spatial (appel VLM séparé pour plus de précision)
    layout_desc = describe_spatial_layout(path_to_image)

    # Étape 2 : extraire la liste propre d'objets
    object_list = extract_object_list(detection_text, prompt)

    if not object_list:
        print("[V3] Aucun objet extrait.")
        return []

    # Étape 3 : matcher au catalogue
    objet_reconnus, non_reconnus = match_to_catalogue(object_list)

    if non_reconnus:
        print(f"[V3] Objets non reconnus dans le catalogue : {non_reconnus}")

    if not objet_reconnus:
        return []

    # Étape 4 : positionner en respectant le layout de l'image
    return object_dim_quat_from_image(layout_desc, objet_reconnus)


# ─────────────────────────────────────────────
#  Test rapide
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    image_path = sys.argv[1] if len(sys.argv) > 1 else None
    user_prompt = sys.argv[2] if len(sys.argv) > 2 else None

    if not image_path and not user_prompt:
        print("Usage: python promptToJson_V3_im.py <image_path> [prompt]")
        sys.exit(1)

    scene = get_scene_from_image(image_path, user_prompt)
    print("\n=== Scène générée ===")
    print(json.dumps(scene, indent=2, ensure_ascii=False))
