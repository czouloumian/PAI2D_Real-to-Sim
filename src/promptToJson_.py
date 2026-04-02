import requests
import json
import os
import re

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

OBJETS_DIR =  os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "objets"))
url = "http://localhost:11434/api/generate"

def get_dimensions(obj_path):
  """ dimension d'un objets pour le placement"""
  bbox_path = os.path.join(obj_path, "bounding_box.json")
  if not os.path.isfile(bbox_path):
      return None
  with open(bbox_path) as f:
      bbox = json.load(f)
  return [round(bbox["max"][i] - bbox["min"][i], 4) for i in range(3)]

def objets_list(dirpath=OBJETS_DIR):
  """liste des objets avec leur nom, leur dimension, et leur path"""
  result = {}
  for obj in os.listdir(dirpath):
    if obj.startswith("."):
      continue
    obj_path = os.path.join(dirpath, obj)
    nom_obj = obj.replace("_"," ") 
    nom_obj = re.sub(r'[@#$%^&*1234567890]', '', nom_obj)
    result[obj] = {
      "name": nom_obj ,
      "path": obj_path,
      "dimensions": get_dimensions(obj_path)  # [x, y, z] en mètres, ou None si non disponible
    }
  return result
  
#print(objets_list(OBJETS_DIR)["10211_ordinateur_portable"])

def gestion_erreur(payload):
  try:
    response = requests.post(url, json=payload, timeout=90)
  except requests.exceptions.ConnectionError:
    raise ConnectionError("Impossible de joindre Ollama. Lancez : ollama serve")

  if response.status_code != 200:
    raise RuntimeError(f"Erreur Ollama (HTTP {response.status_code}): {response.text}")
  raw = response.json()["response"]
  
  json_match = re.search(r"\{.*\}", raw, re.DOTALL)
  if not json_match:
    raise ValueError("Le LLM n'a pas retourné de JSON valide")

  return json_match


def validate_matches(result, objects_data):
  """Vérifie par le LLM que chaque mapping label urdf est sémantiquement cohérent.
  Retourne ([(label, urdf), ...] valides, [labels] rejetés)"""
  reconnus = result.get("obj_reconnus", {})
  # convertit le dict {label: urdf} en paires, en filtrant les urdfs inexistants
  matches = [(label, urdf) for label, urdf in reconnus.items() if urdf in objects_data]
  if not matches:
    return [], list(reconnus.keys())

  pairs_desc = "\n".join(
    f'{i+1}. "{label}" => "{objects_data[urdf]["name"].strip()}"'
    for i, (label, urdf) in enumerate(matches)
  )

  system = """You verify semantic matches between a scene label and a catalogue object name.
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

  Return ONLY: {"verdicts": [true, false, ...]} — one boolean per pair, in order."""

  payload = {
    "model": "phi3:mini",
    "system": system,
    "prompt": pairs_desc,
    "stream": False,
    "format": "json",
    "options": {"temperature": 0}
  }

  json_match = gestion_erreur(payload)
  verdicts = json.loads(json_match.group()).get("verdicts", [])

  accepted = []
  rejected = []
  for i, (label, urdf) in enumerate(matches):
    if i < len(verdicts) and verdicts[i]:
      accepted.append((label, urdf))
    else:
      print(f"[validation] rejeté: '{label}' ≠ '{objects_data[urdf]['name'].strip()}'")
      rejected.append(label)

  return accepted, rejected


def object_rec(prompt=None):
  """donne la liste des objets reconnus sous la forme 
  obj : { 
    id : lave linge 
    "urdf": "11826_lave_linge",
    "path" :  "/Users/anaisazouaoui/Desktop/PAI2D/projet Real-to-Sim/PAI2D_Real-to-Sim/src/../objets/11826_lave_linge/mobility.urdf",
    dimension : "[1.4671, 0.824, 1.0456]"
  }
  ensuite on injectera le resultat dans une nouvelle fonction avec le prompt pour determiner les coordonnées et les quaternions
  """
  # recuperer la liste des noms d'objets 
  list_name=[]
  objects_data = objets_list(dirpath=OBJETS_DIR)
  for key,value in objects_data .items():
    list_name.append(value["name"])
  #print(list_name)

  if not prompt:
    objet_reconnus = {}
    return objet_reconnus

  objects_desc = "\n".join(
    f'- urdf: "{k}" | nom: "{v["name"].strip()}" | dimensions: {v["dimensions"]} m'
    for k, v in objects_data.items()
    if v["dimensions"] is not None
  )

  system_prompt = f"""You are a strict JSON API that matches objects from a scene description to a fixed catalogue of 3D models.

CATALOGUE — the ONLY valid "urdf" values:
{objects_desc}

EXAMPLES:
Input: "un frigo et une machine à laver côte à côte"
Output: {{"objets_non_reconnus": [], "obj_reconnus": {{"frigo": "10143_refrigerateur", "machine à laver": "11826_lave_linge"}}}}

Input: "une chaise et un four"
Output: {{"objets_non_reconnus": ["chaise"], "obj_reconnus": {{"four": "7138_four"}}}}

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
  valid_urdfs = set(objects_data.keys())

  for attempt in range(3): # 3 essaie pour que le LLM tente de reconnaitre les objets, sinon l'utilisateur interviendra
    payload = {
      "model": "phi3:mini",
      "system": system_prompt,
      "prompt": user_prompt,
      "stream": False,
      "format": "json",
      "options": {"temperature": 0}
    }

    json_match = gestion_erreur(payload)
    result = json.loads(json_match.group())

    # obj_reconnus est maintenant un dict {label: urdf}
    invalid = [urdf for urdf in result.get("obj_reconnus", {}).values()
               if urdf not in valid_urdfs]
    if not invalid:
      break
    print(f"[retry {attempt + 1}] urdfs invalides : {invalid}")
    user_prompt = prompt + f"\nPREVIOUS ERROR: these urdfs do not exist: {invalid}. Remove or correct them."

  # Contrôle sémantique : vérifier que chaque label correspond vraiment à l'objet mappé
  valid_matches, rejected_labels = validate_matches(result, objects_data)
  non_reconnus = result.get("objets_non_reconnus", []) + rejected_labels

  objet_reconnus = {}
  for label, urdf in valid_matches:
    objet_reconnus[label] = {
      "urdf": urdf,
      "path": objects_data[urdf]["path"],
      "dimensions": objects_data[urdf]["dimensions"]
    }

  print("Reconnus:", objet_reconnus)
  print("Non reconnus:", non_reconnus)
  return objet_reconnus, non_reconnus

def object_dim_quat(prompt,objet_reconnus):
  """retourne la liste des objets avec les dimensions et quaternions
  forme : 
  {
  "id": "poubelle",
  "urdf": "10357_poubelle",
  "path": "/Users/anaisazouaoui/Desktop/PAI2D/projet Real-to-Sim/PAI2D_Real-to-Sim/src/../objets/10357_poubelle/mobility.urdf",
  "scale": 0.26,
  "quat": [0.7071,0.0,0.0,0.7071],
  "pos": [0.0,0.0,1.07]
  }
  """
  objects_desc = "\n".join(
    f'- id: "{id_}" | urdf: "{info["urdf"]}" | dimensions réelles: {info["dimensions"]} m [x, y, z]'
    for id_, info in objet_reconnus.items()
  )

  system_prompt = f"""You are a strict JSON API. You place 3D objects in a simulation scene.
  All dimensions are in meters. The floor is at z = 0. 

  OBJECTS TO PLACE:
  {objects_desc}

  OUTPUT FORMAT — return ONLY this JSON object:
  {{
    "objects": [
      {{
        "id": "<object id>",
        "urdf": "<urdf name>",
        "scale": <float>,
        "quat": [<w>, <x>, <y>, <z>],
        "pos": [<x>, <y>, <z>]
      }}
    ]
  }}

  STRICT RULES:
  - "id" and "urdf" must be copied verbatim from the objects list above
  - scale: adjust so the object looks realistic in the scene (1.0 = use real dimensions as-is)
  - quat: orientation as [w, x, y, z] — default orientation = [0.7071,0.0,0.0,0.7071]
  - pos z: set to half of (dimensions[2] * scale) so the object rests on the floor
  - objects must NOT overlap — space them according to the scene description
  - output raw JSON only, no markdown, no comments, no explanation"""

  payload = {
    "model": "phi3:mini",
    "system": system_prompt,
    "prompt": prompt,
    "stream": False,
    "format": "json",
    "options": {"temperature": 0}
  }

  json_match = gestion_erreur(payload)
  objetList = json.loads(json_match.group()).get("objects", [])

  for obj in objetList:
    if obj["id"] in objet_reconnus:
      obj["path"] = objet_reconnus[obj["id"]]["path"]

  print(json.dumps(objetList, indent=2))
  return objetList


# interaction utilisateur : lister les objets reconnus, demander a l'utilisateur une confirmation. Si il y a des objets non reconnus,
# les listes aussi avec une lsite d'objets proche que l'utilisateur peut choisir à la place 

#user_prompt = "place une poubelle sur un lave linge"
#objets_reconnus, non_reconnus = object_rec(user_prompt)
#print("Reconnus:", objets_reconnus)
#print("Non reconnus:", non_reconnus)
#objetList = object_dim_quat(user_prompt,objets_reconnus)
#print(json.dumps(objetList, indent=2))



