import requests
import json
import re
from .catalogue import objects_desc, objets_list

URL = "http://localhost:11434/api/generate"

# regex compilee une seule fois au chargement du module
RE_JSON = re.compile(r"\{.*\}", re.DOTALL)


def validate_json_response(payload):
  try:
    response = requests.post(URL, json=payload, timeout=300)
  except requests.exceptions.ConnectionError:
    raise ConnectionError("Impossible de joindre Ollama.")

  if response.status_code != 200:
    raise RuntimeError(f"Erreur Ollama (HTTP {response.status_code}): {response.text}")
  raw = response.json().get("response", "")

  json_match = RE_JSON.search(raw)
  if not json_match:
    raise ValueError("Le LLM n'a pas retourne de JSON valide")

  result = json.loads(json_match.group()) # transforme en dictionnaire

  return result


def classify_intent(prompt, scene_summary):
  """Classifie le prompt en 'modify_scene' ou 'new_scene'."""
  system_prompt = f"""You classify user instructions about a 3D scene.

        Current scene: {scene_summary}

        If the user wants to MODIFY the existing scene (move, remove, add, rotate, resize objects), return: {{"intent": "modify_scene"}}
        If the user wants to CREATE a completely new scene (ignoring the current one), return: {{"intent": "new_scene"}}

        Return ONLY raw JSON, no markdown, no comments."""

  payload = {
    "model": "llama3.1",
    "system": system_prompt,
    "prompt": prompt,
    "stream": False,
    "format": "json",
    "options": {"temperature": 0}
  }

  result = validate_json_response(payload)
  intent = result.get("intent", "new_scene")
  return intent if intent in ("modify_scene", "new_scene") else "new_scene"


def suggest_alternatives(label):
  """Propose 2-3 objets du catalogue les plus proches du label non reconnu"""
  catalog_desc = objects_desc()
  objects_data = objets_list()

  system_prompt = f"""You suggest the closest alternatives from a 3D object catalogue for an unrecognized object.

        CATALOGUE:
        {catalog_desc}

        Return ONLY this JSON: {{"alternatives": ["urdf_key_1", "urdf_key_2"]}}
        - Pick the 2-3 closest matches (same category or similar function)
        - If nothing is remotely close, return {{"alternatives": []}}
        - Each value must be an exact urdf key from the catalogue
        - output raw JSON only, no markdown, no comments"""

  payload = {
    "model": "llama3.1",
    "system": system_prompt,
    "prompt": f'The user asked for: "{label}"',
    "stream": False,
    "format": "json",
    "options": {"temperature": 0}
  }

  alternatives = validate_json_response(payload)
  # filtrer les URDFs invalides
  return [a for a in alternatives if a in objects_data]
