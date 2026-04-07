from promptToJson_auxilieres import validate_json_response, object_rec
import re

#---------------------------------------------------------------------
# RECONNAITRE LES RELATIONS ENTRE OBJETS
#---------------------------------------------------------------------

VALID_RELATION_TYPES = {"on", "under", "left_of", "right_of", "in_front_of", "behind", "facing"}


def _normalize(s):
  """Normalise un ID pour le matching flou : minuscules, espaces/tirets/_"""
  s = s.lower().strip()
  s = re.sub(r'[-_\s]+', ' ', s)
  return s


def fuzzy_match(raw_id, valid_ids):
  """Essaie de trouver l'ID valide le plus proche du raw_id retourne par le LLM"""
  if raw_id in valid_ids:
    return raw_id

  norm_raw = _normalize(raw_id)
  # "lave-linge" == "lave linge" normalisation
  for vid in valid_ids:
    if _normalize(vid) == norm_raw:
      return vid

  # le LLM a peut-être ajoute/retire des mots)
  for vid in valid_ids:
    nv = _normalize(vid)
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


def object_relations(prompt=None, objets_rec=None):
  """
  param:
    prompt : prompt utilisateur
    objets_rec : dict des objets reconnus {id: {urdf, path, dimensions}}

  retourne : dict {"root": "<id>", "relations": [{"type": ..., "subject": ..., "object": ...}]}
  """

  ids = list(objets_rec.keys())
  objects_list_str = "\n".join(f'- "{id_}"' for id_ in ids)
  print(objects_list_str)

  if not prompt or not objets_rec:
    return {"root": ids[0] if ids else "", "relations": []}

  system_prompt = f"""You are a strict JSON API that extracts spatial relations between objects from a scene description.

        OBJECTS IN THE SCENE — use ONLY these exact ids (copy them exactly, character by character):
        {objects_list_str}

        RELATION TYPES (the only allowed values for "type"):
        - "on"          : A rests on top of B              (e.g. "a book on the table")
        - "under"       : A is below B                     (e.g. "a rug under the sofa")
        - "left_of"     : A is to the left of B            (e.g. "the lamp left of the desk")
        - "right_of"    : A is to the right of B           (e.g. "the chair right of the bed")
        - "in_front_of" : A is in front of B               (e.g. "a chair in front of a desk")
        - "behind"      : A is behind B                    (e.g. "a plant behind the sofa")
        - "facing"      : A and B face each other          (e.g. "two sofas facing each other")

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


if __name__ == "__main__":
  user_prompt = "je veux un poubelle sur un lave linge "
  objets_rec, objets_non_rec = object_rec(user_prompt)
  resultat = object_relations(user_prompt, objets_rec)
  print(resultat)
