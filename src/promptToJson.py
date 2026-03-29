import requests
import json
import os
import re

url = "http://localhost:11434/api/generate"

OBJETS_DIR = os.path.join(os.path.dirname(__file__), "..", "objets")


def get_available_objects(objets_dir=OBJETS_DIR):
    """Retourne la liste des dossiers d'objets disponibles dans objets"""
    return [
        d for d in os.listdir(objets_dir)
        if os.path.isdir(os.path.join(objets_dir, d))
        and not d.startswith(".")
    ]


#print(get_available_objects(OBJETS_DIR))

def instruction_to_json(instruction, output_file="scene_2.json"):
    """
    Generer un fichier json a partir d'un prompt
    """
    available_objects = get_available_objects()
    objects_list = ", ".join(available_objects)

    prompt = f"""
You convert natural language scene descriptions into structured JSON.
Instruction:
{instruction}

Available objects — the COMPLETE list, nothing else exists:
{objects_list}

Return ONLY a JSON object with this exact structure:
{{
  "objets_non_reconnus": ["word1", "word2"],
  "objects": [
    {{
      "id": "string",
      "urdf": "exact_folder_name_from_list",
      "mass": 0.0,
      "taille": 1.0,
      "root": true
    }},
    {{
      "id": "string",
      "urdf": "exact_folder_name_from_list",
      "mass": 0.0,
      "taille": 1.0
    }}
  ],
  "relations": [
    {{
      "type": "string",
      "subject": "object_id",
      "object": "object_id"
    }}
  ]
}}
STRICT Rules:
- only JSON, no explanations
- "objets_non_reconnus": list every object word from the instruction that does NOT have a clear, direct semantic match in the available list — use an empty list [] if all objects are matched
- FORBIDDEN: substituting an unavailable object with a different object (e.g. do NOT map "livre" to "boite_carton_ouverte", do NOT map "chaise" to "poubelle")
- ONLY include an object in "objects" if it has a genuine, obvious semantic match in the available list
- the "urdf" field must be EXACTLY one of the folder names from the available list
- the first object in "objects" must have "root": true, others must NOT have a "root" field
- relations allowed: on, left_of, right_of, facing, behind, in_front_of, under
- mass must be a positive number in kilograms, estimate realistically
- taille is a relative scale factor (1.0 = normal size, 0.5 = half size, 2.0 = double size), estimated relative to other objects
"""

    payload = {
        "model": "phi3:mini",
        "prompt": prompt,
        "stream": False
    }

    try:
        response = requests.post(url, json=payload, timeout=90)
    except requests.exceptions.ConnectionError:
        raise ConnectionError(
            "Impossible de joindre Ollama sur localhost:11434. "
            "Assurez-vous qu'Ollama est lance avec : ollama serve"
        )

    if response.status_code != 200:
        raise RuntimeError(f"Erreur Ollama (HTTP {response.status_code}): {response.text}")

    raw = response.json()["response"]
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError("Le LLM n'a pas retourne de JSON valide. Essayez de reformuler.")

    try:
        scene_json = json.loads(match.group())
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON invalide genere par le LLM: {e}")

    non_reconnus = scene_json.pop("objets_non_reconnus", [])

    available_set = set(available_objects)
    invalid = [obj["urdf"] for obj in scene_json.get("objects", []) if obj.get("urdf", "") not in available_set]
    if invalid:
        raise ValueError(f"URDFs invalides generes par le LLM : {', '.join(invalid)}")

    if not scene_json.get("objects"):
        raise ValueError("Aucun objet reconnu dans la bibliotheque. Essayez avec une description differente.")

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(scene_json, f, indent=2)


if __name__ == "__main__":
    instruction = "un livre et un arbre a sa gauche avec deux chaises cote a cote sur la droite du livre"
    scene_json, non_reconnus = instruction_to_json(instruction)
    if non_reconnus:
        print("Objets non reconnus:", non_reconnus)
    print(json.dumps(scene_json, indent=2))