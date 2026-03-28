
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


#TODO: une fonction plus propre pour sauvegarder le json corrigé et au propre


def validate(prompt, jsonFile, path_to_image, max_iter=5):
    """
    On demande au VLM de valider la scene en la comparant au prmpt original.

    :param prompt: le prompt de l'utilisateur
    :param jsonFile: le fichier JSON contenant les informations sur la scène
    :param path_to_image: le chemin vers la capture d'écran de la scène générée
    :return: le nouveau JSON (donc une correction par rapport à l'ancien) et une validation (vraie si la scene semble correcte et fausse dans le cas contraire)
    """
    
    #le system prompt pour dire au VLM quoi faire en general pour la validation
    system_prompt="""You are a 3D Layout Expert. Your task is to correct the placement of objects based on USER INTENT.
                    
                    Your task:
                    1. Look at the screenshot of a 3D scene
                    2. Compare it to the original prompt
                    3. Output a corrected JSON scene if needed


                    GEOMETRIC RULES:
                    1. THE 'ON' RULE: To place Object A ON Object B:
                    - A.pos[2] (height) MUST BE: B.pos[2] + (B.dimensions[2]/2) + (A.dimensions[2]/2).
                    - A.pos[0] and A.pos[1] must be within the range of B's dimensions.
                    - the X and Y must be very close (< 0.1) for A and B.
                    2. FLOOR RULE: If an object is on the floor, its Z-position is exactly Height/2.
                    3. AXES: X is horizontal, Y is depth (forward/backward), Z is vertical (up/down).

                    You will receive:
                    - The original text prompt describing the scene
                    - The current scene as a JSON object
                    - a collage containing THREE images of the same scene:
                        1. PERSPECTIVE VIEW: General context.
                        2. TOP-DOWN VIEW: Best for X, Y coordinates and checking if objects are side-by-side.
                        3. SIDE VIEW: Best for Z coordinate (height) to check if objects are floating or clipping into the floor.

                    You MUST respond with ONLY a valid JSON object, exactly in this format:
                    {
                        "valid": true,
                        "feedback": "scene is correct",
                        "new_scene": {
                            "objets": [
                                {"id": "mug", "urdf": "mug.urdf", "pos": [0.0, 0.5, 0.3], "quat": [0.0, 0.0, 0.0, 1.0]},
                                {"id": "table", "urdf": "table.urdf", "pos": [0.0, 0.0, 0.0], "quat": [0.0, 0.0, 0.0, 1.0]}
                            ]
                        }
                    }

                    RULES:
                    - ONLY output the JSON object, nothing else
                    - NO markdown, NO backticks, NO explanations before or after
                    - Always use double quotes for keys and strings
                    - Always use lowercase true/false
                    - Keep the same "id" and "urdf" values as the input JSON
                    - Keep the same number of objects as the input JSON, do not add or remove objects
                    - Only change "pos" and "quat" values to fix the scene
                    - DO NOT change 'id', 'urdf', or 'path'.
                    - If valid is true, new_scene can be identical to the input
                    - ALWAYS include the "new_scene" field, even if the scene is valid
                    - There should NOT be ANY collisions
                    - If the image shows a gap between objects that should be touching, 'valid' is FALSE.
                    - If objects overlap (clipping), 'valid' is FALSE."""


    #TODO: les criteres de validation pour que la cene soit consideree valide ou pas par le vlm pourraient etre plus precises et specifiees dans le system prompt

    resultat_validation = {"valid": False, "feedback": "Les boucles n'ont pas commencé"}

    for i in range(max_iter):

        print("feedback boucle", i, ":", resultat_validation.get('feedback', 'pas de feedback donné'))
        with open(jsonFile, 'r') as file:
            data = json.load(file)
        itemsList = data.get('objets', [])
        itemsList = getFilePath(itemsList) #TODO: a changer plus tard
        image_paths = create_scene(itemsList)

        reponse = ollama.chat(
            model="llama3.2-vision",
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user','content': f'Original prompt: {prompt}\n Current JSON scene: {json.dumps(data)}\nDoes the image match the prompt? If not, correct the JSON.','images': [path_to_image] }
            ]
        )

        resultat = reponse['message']['content']
        resultat = re.sub(r'```json|```', '', resultat) 
        resultat = resultat.strip()
        resultat = resultat.replace("'", '"') 
        resultat = resultat.replace('True', 'true').replace('False', 'false')
        start = resultat.find('{')
        end = resultat.rfind('}') + 1
        if start != -1 and end != 0:
            resultat = resultat[start:end]

        print("RÉPONSE BRUTE DU VLM:", resultat)
        try:
            resultat_validation = json.loads(resultat)
        except json.JSONDecodeError:
            print("JSON invalide généré par le VLM")
            continue

        if 'new_scene' not in resultat_validation:
            if 'objets' in resultat_validation:
                items = resultat_validation['objets']
                with open(jsonFile, 'w') as file:
                    json.dump({'objets': items}, file)
                print(f"JSON mis à jour: {items}")
            else:
                print("Champ new_scene manquant, on continue")
            continue

        items = resultat_validation['new_scene']['objets']
        items = getFilePath(items)
        items = getOriginalDimensions(items)

        if not checkOverlap(items): #s'il y a overlap
            resultat_validation['valid'] = False
            continue

        if resultat_validation['valid']:
            print(f"Scène validée après {i+1} itérations")
            with open(jsonFile, 'w') as file:
                json.dump({'objets': items}, file, indent=4)
            return resultat_validation
        #si pas valide,ça met à jour le json pour la prochaine itération
        with open(jsonFile, 'w') as file:
            json.dump({'objets': items}, file)

        print(f"JSON mis à jour: {items}")
    
    return resultat_validation