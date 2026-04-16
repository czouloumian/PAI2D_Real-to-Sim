from promptToJson_auxilieres import validate_json_response, object_rec
import re

#---------------------------------------------------------------------
# RECONNAITRE LES RELATIONS ENTRE OBJETS
#---------------------------------------------------------------------

VALID_RELATION_TYPES = {"on", "under", "left_of", "right_of", "in_front_of", "behind", "facing", "against", "inside"}


def normalize(s):
  """Normalise un ID pour le matching flou : minuscules, espaces/tirets/_"""
  s = s.lower().strip()
  s = re.sub(r'[-_\s]+', ' ', s)
  return s


def fuzzy_match(raw_id, valid_ids):
  """Essaie de trouver l'ID valide le plus proche du raw_id retourne par le LLM"""
  if raw_id in valid_ids:
    return raw_id

  norm_raw = normalize(raw_id)
  # "lave-linge" == "lave linge" normalisation
  for vid in valid_ids:
    if normalize(vid) == norm_raw:
      return vid

  # le LLM a peut-etre ajoute/retire des mots cet idiot 
  for vid in valid_ids:
    nv = normalize(vid)
    if nv in norm_raw or norm_raw in nv:
      return vid

  return None


def fix_ids_in_result(result, valid_ids):
  """Corrige le root et les IDs des relations pour qu'ils correspondent aux ID"""
  ids_list = list(valid_ids)

  # corriger root
  root = result.get("root", "")
  matched_root = fuzzy_match(root, valid_ids)
  if matched_root:
    if matched_root != root:
      print(f"[object_relations] root '{root}' -> corrigé en '{matched_root}'")
    result["root"] = matched_root
  else:
    print(f"[object_relations] root '{root}' introuvable, fallback sur '{ids_list[0]}'")
    result["root"] = ids_list[0]

  # corriger les relations
  fixed_relations = []
  for rel in result.get("relations", []):
    rel_type = rel.get("type", "")
    if rel_type not in VALID_RELATION_TYPES:
      print(f"[object_relations] Relation ignorée (type invalide '{rel_type}') : {rel}")
      continue

    subj = rel.get("subject", "")
    obj = rel.get("object", "")
    matched_subj = fuzzy_match(subj, valid_ids)
    matched_obj = fuzzy_match(obj, valid_ids)

    if not matched_subj or not matched_obj:
      print(f"[object_relations] Relation ignorée (ID non résolu) : {rel}")
      continue

    if matched_subj != subj:
      print(f"[object_relations] subject '{subj}' → corrigé en '{matched_subj}'")
    if matched_obj != obj:
      print(f"[object_relations] object '{obj}' → corrigé en '{matched_obj}'")

    rel["subject"] = matched_subj
    rel["object"] = matched_obj
    fixed_relations.append(rel)

  result["relations"] = fixed_relations
  return result

objets_test  = {'poubelle': {'urdf': '10357_poubelle', 'path': '/Users/anaisazouaoui/Desktop/PAI2D/projet Real-to-Sim/PAI2D_Real-to-Sim/objets/10357_poubelle', 'dimensions': [1.1516, 1.7345, 1.1516]}, 'refrigerateur': {'urdf': '10143_refrigerateur', 'path': '/Users/anaisazouaoui/Desktop/PAI2D/projet Real-to-Sim/PAI2D_Real-to-Sim/objets/10143_refrigerateur', 'dimensions': [0.8589, 1.5259, 0.9222]}, 'machine à laver': {'urdf': '11826_lave_linge', 'path': '/Users/anaisazouaoui/Desktop/PAI2D/projet Real-to-Sim/PAI2D_Real-to-Sim/objets/11826_lave_linge', 'dimensions': [1.1075, 1.5321, 0.9968]}, 'toaster': {'urdf': '103477_toaster', 'path': '/Users/anaisazouaoui/Desktop/PAI2D/projet Real-to-Sim/PAI2D_Real-to-Sim/objets/103477_toaster', 'dimensions': [1.0363, 1.0794, 1.5112]}}
def scale(prompt,objets_rec):
  """genere les scales des objets relativement"""
  objects_info = "\n".join(
    f'- id: "{id}"| dimensions: {info["dimensions"]} m'
    for id, info in objets_rec.items()
  )
  
  print(["Calcule des scales"])
  
  system_prompt = f"""You are a strict JSON API. You compute realistic scale factors for 3D objects in a simulation scene.

  OBJECTS TO SCALE (current URDF dimensions in meters — these are the raw model dimensions, NOT real-world sizes):
  {objects_info}

  WHAT SCALE MEANS:
  - scale = 1.0  -> keep the model at its current URDF dimensions
  - scale = 0.5  -> make the object half the size of its URDF dimensions
  - scale = 2.0  -> make the object twice the size of its URDF dimensions
  Your goal: choose scale so that the resulting size (dimensions * scale) matches the REAL-WORLD size of the object.

  REAL-WORLD SIZE REFERENCES (approximate, use these to reason):
  - washing machine / lave-linge : ~0.60 x 0.60 x 0.85 m
  - fridge / réfrigérateur        : ~0.70 x 0.70 x 1.80 m
  - dishwasher / lave-vaisselle   : ~0.60 x 0.60 x 0.85 m
  - oven / four                   : ~0.60 x 0.60 x 0.60 m
  - toaster                       : ~0.30 x 0.20 x 0.20 m
  - trash bin / poubelle          : ~0.35 x 0.35 x 0.55 m
  - laptop / ordinateur portable  : ~0.35 x 0.25 x 0.02 m
  - USB key / clé usb             : ~0.07 x 0.02 x 0.01 m
  - drawer / tiroir               : ~0.50 x 0.40 x 0.15 m
  - door / porte                  : ~0.90 x 0.05 x 2.10 m
  - tap / robinet                 : ~0.10 x 0.10 x 0.20 m
  - chest of drawers / meuble     : ~0.80 x 0.45 x 1.00 m

  HOW TO COMPUTE SCALE:
  For each object, find its dominant dimension (longest axis) in the URDF, then:
    scale = real_world_dominant_size / urdf_dominant_size
  Round to 2 decimal places. Keep scale between 0.001 and 5.0.

  ADJUSTMENTS FROM USER PROMPT:
  Read the user's scene description. If the user mentions a size qualifier for an object, adjust its scale:
  - "petit/petite/small/tiny"   → multiply the computed scale by 0.6
  - "grand/grande/big/large"    → multiply the computed scale by 1.5
  - "immense/enormous/giant"    → multiply the computed scale by 2.0
  - "minuscule/tiny/miniature"  → multiply the computed scale by 0.3
  Apply the qualifier only to the object it is explicitly attached to. Do NOT apply it to other objects.

  CONSISTENCY CHECK — before outputting, verify:
  - Scales are mutually coherent: a USB key must be much smaller than a washing machine
  - No two objects of different real-world sizes have the same scale unless their URDF dimensions compensate

  OUTPUT FORMAT — return ONLY this JSON:
  {{
    "scales": {{
      "<id>": <float>,
      "<id>": <float>
    }}
  }}

  EXAMPLES:
  URDF dims: lave-linge=[1.10, 1.53, 1.00], poubelle=[1.15, 1.73, 1.15]
  User: "un lave linge avec une poubelle a cote"
  → lave-linge real ~0.85m tall, urdf 1.00m -> scale ≈ 0.85. poubelle real ~0.55m, urdf 1.15m dominant → scale ≈ 0.48
  Output: {{"scales": {{"lave-linge": 0.85, "poubelle": 0.48}}}}

  URDF dims: lave-linge=[1.10, 1.53, 1.00], poubelle=[1.15, 1.73, 1.15]
  User: "un lave linge avec une petite poubelle a cote"
  → same as above, but "petite" on poubelle -> 0.48 * 0.6 = 0.29
  Output: {{"scales": {{"lave-linge": 0.85, "poubelle": 0.29}}}}

  Output raw JSON only, no markdown, no comments, no explanation."""

  user_prompt = prompt
  payload = {
      "model": "phi3:mini",
      "system": system_prompt,
      "prompt": user_prompt,
      "stream": False,
      "format": "json",
      "options": {"temperature": 0}
    }

  scales = validate_json_response(payload)
  
  print(scales)
  return scales 


def object_relations(prompt=None, objets_rec=None):
  """
  param:
    prompt : prompt utilisateur
    objets_rec : dict des objets reconnus {id: {urdf, path, dimensions}}

  retourne : dict {"root": "<id>", "relations": [{"type": ..., "subject": ..., "object": ...}]}
  """

  ids = list(objets_rec.keys())
  objects_list = "\n".join(f'- "{id}"' for id in ids)
  print(objects_list)

  if not prompt or not objets_rec:
    return {"root": ids[0] if ids else "", "relations": []}

  system_prompt = f"""You are a strict JSON API that extracts spatial relations between objects from a scene description.

        OBJECTS IN THE SCENE — use ONLY these exact ids (copy them exactly, character by character):
        {objects_list}

        RELATION TYPES (the only allowed values for "type"):
        - "on"          : A rests on top of B              (e.g. "a book on the table")
        - "under"       : A is below B                     (e.g. "a rug under the sofa")
        - "left_of"     : A is to the left of B            (e.g. "the lamp left of the desk")
        - "right_of"    : A is to the right of B           (e.g. "the chair right of the bed")
        - "in_front_of" : A is in front of B               (e.g. "a chair in front of a desk")
        - "behind"      : A is behind B                    (e.g. "a plant behind the sofa")
        - "facing"      : A and B face each other          (e.g. "two sofas facing each other")
        - "inside"      : A is inside B                    (e.g. "a book inside the drawer")
        - "against"     : A is against B                   (e.g. "a lamp against the wall")

        OUTPUT FORMAT — return ONLY this JSON:
        {{
          "root": "<id of the largest or most central anchor object>",
          "relations": [
            {{"type": "<relation>", "subject": "<id_A>", "object": "<id_B>"}},
            {{"type": "<relation>", "subject": "<id_A>", "object": "<id_B>"}}
          ]
        }}

        EXAMPLES:
        Scene: "a washing machine with a bin to its right"
        Objects: ["lave-linge", "poubelle"]
        Output: {{"root": "lave-linge", "relations": [{{"type": "right_of", "subject": "poubelle", "object": "lave-linge"}}]}}

        Scene: "a desk with a computer on it, a chair in front"
        Objects: ["bureau", "ordinateur", "chaise"]
        Output: {{"root": "bureau", "relations": [{{"type": "on", "subject": "ordinateur", "object": "bureau"}}, {{"type": "in_front_of", "subject": "chaise", "object": "bureau"}}]}}

        STRICT RULES:
        - "root" must be exactly one id from the list above (copy-paste it exactly)
        - "subject" and "object" must be exact ids from the list above — no other values allowed
        - "type" must be exactly one of: on, under, left_of, right_of, in_front_of, behind, facing
        - only extract relations explicitly stated or clearly implied in the scene description
        - do NOT invent relations that are not mentioned
        - "facing" is symmetric — list it only once per pair
        - if only one object is in the scene, return {{"root": "<id>", "relations": []}}
        - output raw JSON only, no markdown, no comments, no explanation"""

  valid_ids = set(ids)
  user_prompt = prompt

  for attempt in range(3):
    payload = {
      "model": "llama3.1",
      "system": system_prompt,
      "prompt": user_prompt,
      "stream": False,
      "format": "json",
      "options": {"temperature": 0}
    }

    result = validate_json_response(payload)
    result = fix_ids_in_result(result, valid_ids)
    # vérifier que toutes les relations sont valides après correction
    all_ids_ok = all(
      rel["subject"] in valid_ids and rel["object"] in valid_ids
      for rel in result.get("relations", [])
    )
    if result.get("root") in valid_ids and all_ids_ok:
      break

    print(f"[object_relations] retry {attempt + 1} — IDs encore invalides")
    user_prompt = prompt + f"\nIMPORTANT: Use ONLY these exact ids: {ids}. Do NOT modify, translate, or change them in any way."

  print(f"[object_relations] Résultat final : {result}")
  return result



def final_json(objets, scales): 
  
  dict_obj = objets 
  dict_scales = scales['scales']
  
  for key, value in dict_scales.items() :
    dict_obj[key]["scale"] = value
    
  return dict_obj



# objets_test  = {'poubelle': {'urdf': '10357_poubelle', 'path': '/Users/anaisazouaoui/Desktop/PAI2D/projet Real-to-Sim/PAI2D_Real-to-Sim/objets/10357_poubelle', 'dimensions': [1.1516, 1.7345, 1.1516]}, 'refrigerateur': {'urdf': '10143_refrigerateur', 'path': '/Users/anaisazouaoui/Desktop/PAI2D/projet Real-to-Sim/PAI2D_Real-to-Sim/objets/10143_refrigerateur', 'dimensions': [0.8589, 1.5259, 0.9222]}, 'machine à laver': {'urdf': '11826_lave_linge', 'path': '/Users/anaisazouaoui/Desktop/PAI2D/projet Real-to-Sim/PAI2D_Real-to-Sim/objets/11826_lave_linge', 'dimensions': [1.1075, 1.5321, 0.9968]}, 'toaster': {'urdf': '103477_toaster', 'path': '/Users/anaisazouaoui/Desktop/PAI2D/projet Real-to-Sim/PAI2D_Real-to-Sim/objets/103477_toaster', 'dimensions': [1.0363, 1.0794, 1.5112]}}
# user_prompt = "je veux un poubelle sur un lave linge et derrier un refrigeratuer et une petite machine a laver.  "
# scales = {'scales': {'poubelle': 0.35, 'refrigerateur': 1.27, 'machine à laver': 0.68}}
# print(final_json(objets_test, scales))


# user_prompt = "je veux un poubelle sur un lave linge "
# objets_rec, objets_non_rec = object_rec(user_prompt)
# resultat = object_relations(user_prompt, objets_rec)
# print(resultat)

