import re


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
