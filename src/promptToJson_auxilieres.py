import requests
import json
import os
import re
import functools

OBJETS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "objets"))
URL = "http://localhost:11434/api/generate"

# regexes compilées une seule fois au chargement du module
_RE_JSON = re.compile(r"\{.*\}", re.DOTALL)
_RE_STRIP = re.compile(r'[@#$%^&*\d]')


#---------------------------------------------------------------------
# fonctions auxilieres
#---------------------------------------------------------------------

def get_dimensions(obj_path):
  """ dimension d'un objets pour le placement"""
  bbox_path = os.path.join(obj_path, "bounding_box.json")
  if not os.path.isfile(bbox_path):
      return None
  with open(bbox_path) as f:
      bbox = json.load(f)
  return [round(bbox["max"][i] - bbox["min"][i], 4) for i in range(3)]


@functools.lru_cache(maxsize=1)
def objets_list(dirpath=OBJETS_DIR):
  """liste des objets avec leur nom, leur dimension, et leur path — cache pour pas refaire le calcule"""
  result = {}
  with os.scandir(dirpath) as it:
    for entry in it:
      if entry.name.startswith(".") or not entry.is_dir():
        continue
      nom_obj = _RE_STRIP.sub('', entry.name.replace("_", " "))
      result[entry.name] = {
        "name": nom_obj,
        "path": entry.path,
        "dimensions": get_dimensions(entry.path)
      }
  return result


@functools.lru_cache(maxsize=1)
def objects_desc(dirpath=OBJETS_DIR):
  """chaine de description du catalogue — cache pour pas refaire le calcule"""
  objects_data = objets_list(dirpath)
  return "\n".join(
    f'- urdf: "{k}" | nom: "{v["name"].strip()}" | dimensions: {v["dimensions"]} m'
    for k, v in objects_data.items()
    if v["dimensions"] is not None
  )


def validate_json_response(payload):
  try:
    response = requests.post(URL, json=payload, timeout=300)
  except requests.exceptions.ConnectionError:
    raise ConnectionError("Impossible de joindre Ollama.")

  if response.status_code != 200:
    raise RuntimeError(f"Erreur Ollama (HTTP {response.status_code}): {response.text}")
  raw = response.json().get("response", "")

  json_match = _RE_JSON.search(raw)
  if not json_match:
    raise ValueError("Le LLM n'a pas retourné de JSON valide")
  
  result = json.loads(json_match.group()) # transforme en dictionnaire 

  return result


def validate_matches(result, objects_data):
  """Vérifie par le LLM que chaque mapping label urdf est cohérent
  Retourne ([(label, urdf), ...] valides, [labels] rejetés)"""
  reconnus = result.get("obj_reconnus", {})
  matches = [(label, urdf) for label, urdf in reconnus.items() if urdf in objects_data]
  if not matches:
    return [], list(reconnus.keys())

  pairs_desc = "\n".join(
    f'{i+1}. "{label}" => "{objects_data[urdf]["name"].strip()}"'
    for i, (label, urdf) in enumerate(matches)
  )

  system_prompt = """You verify semantic matches between a scene label and a catalogue object name.
        For each numbered pair, answer: does the label refer to the SAME TYPE of real-world object?

        Examples of TRUE matches (synonyms or same object):
        "frigo" => "refrigerateur" = true
        "machine à laver" => "lave linge" = true
        "ordi" => "ordinateur portable" = true
        "poubelle" => "poubelle" = true

        Examples of FALSE matches (different objects):
        "baignoire" => "ordinateur portable" = false
        "chaise" => "poubelle" = false
        "table" => "four" = false
        "lit" => "toaster" = false
        "table" => "meuble tiroirs" = false

        Return ONLY: {"verdicts": [true, false, ...]} — one boolean per pair, in order."""

  payload = {
    "model": "llama3.1",
    "system": system_prompt,
    "prompt": pairs_desc,
    "stream": False,
    "format": "json",
    "options": {"temperature": 0}
  }

  raw_verdicts = validate_json_response(payload).get("verdicts", [])
  
  # normaliser : le LLM retourne parfois un bool au lieu d'une liste
  if isinstance(raw_verdicts, bool):
    verdicts = [raw_verdicts]
  elif isinstance(raw_verdicts, list):
    verdicts = raw_verdicts
  else:
    verdicts = []

  accepted = []
  rejected = []
  for i, (label, urdf) in enumerate(matches):
    if i < len(verdicts) and verdicts[i]:
      accepted.append((label, urdf))
    else:
      print(f"[validation] rejeté: '{label}' ≠ '{objects_data[urdf]['name'].strip()}'")
      rejected.append(label)

  return accepted, rejected


#---------------------------------------------------------------------
# RECONNAISSANCE D'OBJETS AVEC PROMPT TEXTUEL
#---------------------------------------------------------------------

def object_rec(prompt=None):
  """
  param:
    prompt : prompt utilisateur

  retourne : dict des objets reconnus {id: {urdf, path, dimensions}}
  """
  
  objects_data = objets_list()  
  valid_urdfs = set(objects_data.keys())
  objects_desc = objects_desc()  
  
  #print(objects_desc)
  
  if not prompt:
    return {}, []

  system_prompt = f"""You are a strict JSON API that matches objects from a scene description to a fixed catalogue of 3D models.

        CATALOGUE — the ONLY valid "urdf" values:
        {objects_desc}

        EXAMPLES:
        Input: "un frigo et une machine à laver côte à côte"
        Output: {{"objets_non_reconnus": [], "obj_reconnus": {{"frigo": "10143_refrigerateur", "machine à laver": "11826_lave_linge"}}}}

        Input: "une chaise et un four"
        Output: {{"objets_non_reconnus": ["chaise"], "obj_reconnus": {{"four": "7138_four"}}}}
        
        Input: "deux toasters derriere une machine a laver"
        Output: {{"objets_non_reconnus": [], "obj_reconnus": {{"toaster_1": "103477_toaster","toaster_2": "103477_toaster","machine à laver": "11826_lave_linge"}}}}

        Input: "une baignoire à côté d'un lave-linge"
        Output: {{"objets_non_reconnus": ["baignoire"], "obj_reconnus": {{"lave-linge": "11826_lave_linge"}}}}
        IMPORTANT: "baignoire" does NOT exist in the catalogue — it must go in objets_non_reconnus, NOT be mapped to an unrelated object.

        OUTPUT FORMAT — return ONLY this JSON:
        {{
          "objets_non_reconnus": ["<unmatched word>"],
          "obj_reconnus": {{
            "<label from scene>": "<exact urdf from catalogue>",
            "<label from scene>": "<exact urdf from catalogue>"
          }}
        }}

        STRICT RULES:
        - each value in "obj_reconnus" must be EXACTLY one of the catalogue entries, copied verbatim
        - include a label in "obj_reconnus" ONLY if it has a DIRECT, OBVIOUS semantic match (same type of object)
        - NEVER substitute an unavailable object with a different one (e.g. do NOT map "baignoire" to "ordinateur_portable")
        - every scene word with no match goes in "objets_non_reconnus"
        - if no object is recognized: {{"objets_non_reconnus": [...], "obj_reconnus": {{}}}}
        - output raw JSON only, no markdown, no comments, no explanation"""

  user_prompt = prompt
  result = {}

  for attempt in range(3):  # 3 essais pour que le LLM tente de reconnaitre les objets
    payload = {
      "model": "llama3.1",
      "system": system_prompt,
      "prompt": user_prompt,
      "stream": False,
      "format": "json",
      "options": {"temperature": 0}
    }

    result = validate_json_response(payload)

    invalid = [urdf for urdf in result.get("obj_reconnus", {}).values()
               if urdf not in valid_urdfs]
    if not invalid:
      break
    print(f"[retry {attempt + 1}] urdfs invalides : {invalid}")
    user_prompt = prompt + f"\nPREVIOUS ERROR: these urdfs do not exist: {invalid}. Remove or correct them."

  # Contrôle sémantique : vérifier que chaque label correspond vraiment à l'objet mappé
  valid_matches, rejected_labels = validate_matches(result, objects_data)
  non_reconnus = result.get("objets_non_reconnus", []) + rejected_labels

  objet_reconnus = {
    label: {
      "urdf": urdf,
      "path": objects_data[urdf]["path"],
      "dimensions": objects_data[urdf]["dimensions"]
    }
    for label, urdf in valid_matches
  }

  print("Reconnus:", objet_reconnus)
  print("Non reconnus:", non_reconnus)
  return objet_reconnus, non_reconnus

#---------------------------------------------------------------------
# SUGGESTION D'ALTERNATIVES
#---------------------------------------------------------------------

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


# premiere phase du prompt : reconnaitre les objets
# objectis :
# - soit le LLM reconnait l'exact objet dans la liste des objets
# - sinon il liste les objets non reconnu et propose les alternatives les plus proches
# - il faut renvoyer les objets et leur paths

# deuxieme phase du prompt :
# - une fois les objets reconnu, on recupere leur dimensions
# - on repasse le prompt corrige avec les dimentions definis et les objets bien adequats

# troisieme phase:
# il faut que le user soit capable de relancer le model, ca doit etre comme une discussion
# une fois que objectList est cree et la scene est generee le user peut demander a changer d'objet
# ou a bouger les objets et le LLM doit etre capable de modifier objetList et refaire

# => objectif final, un Json de la forme :
"""
{
  "id": "lave_linge",
  "urdf": "11826_lave_linge",
  "path": "/Users/anaisazouaoui/Desktop/PAI2D/projet Real-to-Sim/PAI2D_Real-to-Sim/src/../objets/11826_lave_linge/mobility.urdf",
  "scale": 0.55,
  "quat": [0.7071,0.0,0.0,0.7071],
  "pos": [0.0,0.0,0.43]
}
{
  "id": "poubelle",
  "urdf": "10357_poubelle",
  "path": "/Users/anaisazouaoui/Desktop/PAI2D/projet Real-to-Sim/PAI2D_Real-to-Sim/src/../objets/10357_poubelle/mobility.urdf",
  "scale": 0.26,
  "quat": [0.7071,0.0,0.0,0.7071],
  "pos": [0.0,0.0,1.07]
}
"""