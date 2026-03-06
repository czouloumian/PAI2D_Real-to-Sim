import requests
import json

url = "http://localhost:11434/api/generate"

def instruction_to_json(instruction):

    prompt = f"""
you convert natural language scene descriptions into structured JSON 
instruction: {instruction}
return only a JSON object with this exact structure :
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
- only JSON object no other words
- no explanation
- use relations only these relations : on, left_of, right_of, facing, behind, in_front_of, under, 
- every object mentioned must appear in "objects"
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

    try:
        return json.loads(raw)
    except:
        print("invalid JSON returned:")
        print(raw)
        return None


instruction = "un livre et un arbre a sa gauche avec deux chaises cote a cote sur la droitdu livre  "

scene_json = instruction_to_json(instruction)

print(json.dumps(scene_json, indent=2))