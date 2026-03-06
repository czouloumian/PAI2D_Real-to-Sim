import requests
import json
import os
import re

url = "http://localhost:11434/api/generate"

def instruction_to_json(instruction, output_file="scene.json"):
    prompt = f"""
You convert natural language scene descriptions into structured JSON.
Instruction:
{instruction}
Return ONLY a JSON object with this structure:
{{
  "objects": [
    {{
      "id": "string",
      "urdf": "string"
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
Rules:
- only JSON
- no explanations
- relations allowed: on,left_of,right_of,facing,behind,in_front_of,under
"""
    payload = {
      "model": "phi3:mini",
      "prompt": prompt,
      "stream": False
    }

    response = requests.post(url, json=payload)
    if response.status_code != 200:
        raise Exception(response.text)
    raw = response.json()["response"]
    # extrait uniquement le JSON si le modele ajoute du texte comme il pue
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        print("NOPE")
        print(raw)
        return None
    
    json_text = match.group()
    
    try:
        scene_json = json.loads(json_text)
    except json.JSONDecodeError:
        print("JSON invalide généré")
        print(json_text)
        return None

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(scene_json, f, indent=2)
    print("JSON sauvegardé dans :", os.path.abspath(output_file))

    return scene_json

instruction = "un livre et un arbre a sa gauche avec deux chaises cote a cote sur la droite du livre"
scene_json = instruction_to_json(instruction)
if scene_json:
  print(json.dumps(scene_json, indent=2))
  #print(scene_json)