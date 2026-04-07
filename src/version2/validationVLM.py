
import os
import ollama
import json
import re
import xml.etree.ElementTree as ET
import trimesh

from jsonToSim import create_scene

def getFilePath(itemsList):
    '''
    Donne le path pour l'item URDF.

    :param item: le dictionnaire d'item avec id et urdf
    :return path: le path pour l'item
    '''
    items_folder = os.path.join(os.path.dirname(__file__),'..','..', 'objets')
    for item in itemsList:
        item['path'] = os.path.join(items_folder, item['urdf'])
        if not os.path.exists(item['path']):
            raise FileNotFoundError(f"Pour {item['id']}, le fichier {item['urdf']} est introuvable.")

        #TODO: question: pourquoi on cherche d'autres fichiers que mobility.urdf? à changer et à comprendre pour partnet
        #if os.path.isdir(base):
        #    for name in ["mobility.urdf", "kinbody.xml", "textured.obj", "nontextured.stl", "nontextured.ply"]:
        #        path = os.path.join(base, name)
        #        if os.path.exists(path):
        #            return path
        #    raise FileNotFoundError(f"Aucun fichier exploitable trouvé dans {base}")

    return itemsList

def getOriginalDimensions(items):
    '''
    Extrait les dimensions de l'item URDF, qui sont dans '<geometry>'

    :param filepath: le path pour le file urdf
    :return: l'item avec ses dimensions
    '''
    for item in items:
        if item.get('dimensions'):
            continue
        else:
            tree = ET.parse(item['path']) #lecture du fichier urdf en xml
            root = tree.getroot()

            for geometry in root.iter('geometry'):
                box= geometry.find('box')
                cylinder= geometry.find('cylinder')
                sphere= geometry.find('sphere')
                mesh_tag = geometry.find('mesh') #quand les formes sont plus complexes c'est généralement mesh qui est utilisé
                if box is not None:
                    size = box.attrib['size'].split()
                    item['dimensions'] = (float(size[0]),float(size[1]), float(size[2]))
                elif cylinder is not None:
                    r = float(cylinder.attrib['radius'])
                    length = float(cylinder.attrib['length'])
                    item['dimensions'] = (r*2, r*2, length)
                elif sphere is not None:
                    r = float(sphere.attrib['radius'])
                    item['dimensions'] = (r*2, r*2, r*2)
                elif mesh_tag is not None:
                    directory = os.path.dirname(item['path'])
                    path_mesh = os.path.join(directory, mesh_tag.attrib['filename'])
                    mesh = trimesh.load(path_mesh, force='mesh') #force='mesh' est pour ne pas avoir de scene, seulement un mesh unique
                    bounds = mesh.bounding_box.extents
                    item['dimensions'] = (float(bounds[0]),float(bounds[1]),float(bounds[2]))
                else:
                    print("Dimensions non trouvées") #TODO: faire une meilleure erreur
                    item['dimensions'] = (0.1,0.1,0.1)
    return items

def checkOverlap(items):
    for i, item1 in enumerate(items):
        for j, item2 in enumerate(items):
            if i >= j:
                continue
            w1, d1, h1 = item1['dimensions']
            w2, d2, h2 = item2['dimensions']
            x1, y1, z1 = item1['pos']
            x2, y2, z2 = item2['pos']
            
            if (abs(x1-x2) < (w1+w2)/2 and abs(y1-y2) < (d1+d2)/2 and abs(z1-z2) < (h1+h2)/2):
                print(f"overlap détecté entre {item1['id']} et {item2['id']}!")
                return False
    return True


def clean_reponse(resultat):
    resultat = re.sub(r'```json|```', '', resultat) 
    resultat = resultat.strip()
    resultat = resultat.replace("'", '"') 
    resultat = resultat.replace('True', 'true').replace('False', 'false')
    start = resultat.find('{')
    end = resultat.rfind('}') + 1
    if start != -1 and end != 0:
        resultat = resultat[start:end]
    return resultat

def boucle_vlm(user_prompt, jsonFile, image_path, max_iter=5):
    for i in range(max_iter):
        with open(jsonFile, 'r') as file:
            data = json.load(file)
        itemsList = data.get('objets', [])
        itemsList = getFilePath(itemsList) #TODO: a changer plus tard
        image_paths = create_scene(itemsList)

        res = etapes_validation(user_prompt,jsonFile,image_path)
        if res.get("valid")==True:
            print("scene validée")
            return res
        else: #on genere une nouvelle scene apres avoir replacé le json s'il y a bien une nouvelle scene
            print("echec: ", res.get("feedback"))
            if "new_scene" in res:
                with open(jsonFile, 'w') as file:
                    json.dump(res['new_scene']['objets'],file)
            else:
                if 'objets' in res:
                    items = res['objets']
                    with open(jsonFile, 'w') as file:
                        json.dump({'objets': items}, file)
                    print(f"JSON mis à jour: {items}")
                else:
                    print("le llm n'a pas donné de nouvelle scene")
                    continue
        print(f"itération {i+1}: {res}")
    return res


def etapes_validation(original_prompt, jsonFile, image_path):
    #collisions
    prompt1 = """You are a collision detector. Check if the objects overlap. if they do, correct the scene so there is no collision anymore. Only correct the posistion, "pos".

                You will receive:
                    - The current scene as a JSON object
                    - a collage containing THREE images of the same scene:
                        1. PERSPECTIVE VIEW: General context.
                        2. TOP-DOWN VIEW: Best for X, Y coordinates and checking if objects are side-by-side.
                        3. SIDE VIEW: Best for Z coordinate (height) to check if objects are floating or clipping into the floor.

                RULES:
                    - ONLY output the JSON object, nothing else
                    - NO markdown, NO backticks, NO explanations before or after
                    - Always use double quotes for keys and strings
                    - Keep the same "id" and "urdf" values as the input JSON
                    - Keep the same number of objects as the input JSON, do not add or remove objects
                    - Only change "pos" values to fix the scene
                    - DO NOT change 'id', 'urdf', or 'path'.
                    - If valid is true, new_scene can be identical to the input
                    - ALWAYS include the "new_scene" field, even if the scene is valid
                    - There should NOT be ANY collisions
                    - If objects overlap, 'valid' is FALSE.
                        
                You MUST respond with ONLY a valid JSON object, exactly in this format:
                    {
                        "valid": true,
                        "feedback": "scene is correct",
                        "new_scene": {
                            "objets": [
                                {"id": "mug", "urdf": "mug.urdf", "path": "", "pos": [0.0, 0.5, 0.3], "quat": [0.0, 0.0, 0.0, 1.0]},
                                {"id": "table", "urdf": "table.urdf", "path": "", "pos": [0.0, 0.0, 0.0], "quat": [0.0, 0.0, 0.0, 1.0]}
                            ]
                        }
                    }
                """

    resultat1 = ollama.chat(model="llama3.2-vision", messages=[{'role': 'system', 'content': prompt1},
                {'role': 'user','content': f"Check and correct collisions for {json.dumps(jsonFile)}",'images': [image_path]}])
    clean = clean_reponse(resultat1['message']['content'])
    resultat1 = json.loads(clean)
    if not resultat1.get('valid'):
        return resultat1
    

    #semantique
    prompt2 = """ Your role is to verify if the generated scene matches the prompt. If it doesn't, correct the json file descibing the scene so it matches the prompt.

                You will receive:
                    - The current scene as a JSON object
                    - 
                    - a collage containing THREE images of the same scene:
                        1. PERSPECTIVE VIEW: General context.
                        2. TOP-DOWN VIEW: Best for X, Y coordinates and checking if objects are side-by-side.
                        3. SIDE VIEW: Best for Z coordinate (height) to check if objects are floating or clipping into the floor.

                RULES:
                    - ONLY output the JSON object, nothing else
                    - NO markdown, NO backticks, NO explanations before or after
                    - Always use double quotes for keys and strings
                    - Keep the same "id" and "urdf" values as the input JSON
                    - Keep the same number of objects as the input JSON, do not add or remove objects
                    - Only change "pos" values to fix the scene so it matches the prompt.
                    - DO NOT change 'id', 'urdf', or 'path'.
                    - If valid is true, new_scene can be identical to the input
                    - ALWAYS include the "new_scene" field, even if the scene is valid.
                    - If the generated scene doesn't match the prompt, 'valid' is FALSE.

                You MUST respond with ONLY a valid JSON object, exactly in this format:
                    {
                        "valid": true,
                        "feedback": "scene is correct",
                        "new_scene": {
                            "objets": [
                                {"id": "mug", "urdf": "mug.urdf", "path": "", "pos": [0.0, 0.5, 0.3], "quat": [0.0, 0.0, 0.0, 1.0]},
                                {"id": "table", "urdf": "table.urdf", "path": "", "pos": [0.0, 0.0, 0.0], "quat": [0.0, 0.0, 0.0, 1.0]}
                            ]
                        }
                    }
                """

    resultat2 = ollama.chat(model="llama3.2-vision", messages=[{'role': 'system', 'content': prompt2},
                {'role': 'user','content': f"Check and correct if the generated scene {json.dumps(jsonFile)} is accurate to the prompt {original_prompt}.",'images': [image_path]}])
    clean = clean_reponse(resultat2['message']['content'])
    resultat2 = json.loads(clean)
    if not resultat2.get('valid'):
        return resultat2