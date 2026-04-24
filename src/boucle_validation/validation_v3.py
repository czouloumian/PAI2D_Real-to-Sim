
import os
import ollama
import json
import re
import shutil
from datetime import datetime
from .jsonToSim import create_scene_validation, validation_physique
from PIL import Image
import xml.etree.ElementTree as ET
import trimesh
import copy



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

def getOriginalDimensions(items): #TODO: attention c'est pas la meme que dans v1, à changer
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

def save_iteration_scene(image_path, iter, run_dir, itemsList):
    shutil.copy(image_path, os.path.join(run_dir, f"iteration_{iter}_image_v2.png"))
    with open(os.path.join(run_dir, f'iter_{iter}_scene.json'), 'w') as f:
        json.dump({'objets': itemsList}, f, indent=4)

def create_run_dir():
    '''un dossier pour chaque run'''
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'runs', timestamp)
    os.makedirs(run_dir, exist_ok=True)
    return run_dir

def correct_list(data, corrections, field):
    existing_id = {item['id'] for item in data}
    for c_id in corrections.keys():
        if c_id not in existing_id:
            print(f"ATTENTION: l'ID {c_id} n'est pas dans la liste, skipping correction.")
    for item in data:
        if item['id'] in corrections:
            old_value = item[field]
            item[field] = corrections[item['id']]
            print(f"CORRECTION: {field} corrigée pour {item['id']}: {old_value} → {item[field]}")
    return data

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

def boucle_vlm(user_image_path, jsonFile, max_iter=3):
    '''
    Boucle de validation qui compare la scène générée à une image de référence fournie par l'utilisateur.
    '''
    run_dir = create_run_dir()
    history = []

    for iter in range(max_iter):
        
        with open(jsonFile, 'r') as file:
            data = json.load(file)
        
        itemsList = data.get('objets', [])
        itemsList = getOriginalDimensions(itemsList) 

        scene_image_path, corrected_objects = validation_physique(itemsList)

        print("CORRECTED OBJECTS:", corrected_objects)

        save_iteration_scene(scene_image_path, iter, run_dir, itemsList)
        
        # 2. Validation sémantique (VLM compare l'image utilisateur et le screenshot Genesis)
        res, data = etapes_validation(user_image_path, corrected_objects, scene_image_path)
        print(f"DEBUG: les res keys sont {res.keys()} et le contenu est {res}")

        history.append(copy.deepcopy({
            'iteration': iter,
            'feedback': res.get('feedback', ''),
            'corrections': res.get('corrections',''),
            'valid': res.get('valid', False),
            'scene': data
        }))
        
        with open(os.path.join(run_dir, 'history.json'), 'w') as f:
            json.dump(history, f, indent=4)

        if res.get("valid") == True:
            print("Scène validée visuellement et physiquement !")
            return data
        else:
            print("Échec / Corrections en cours : ", res.get("feedback"))

    else:
        print("Nombre maximum d'itérations atteint.")
        return data


def etapes_validation(user_image_path, data, scene_image_path):
    '''
    Envoie l'image cible et l'image de la scène au VLM pour obtenir les corrections de coordonnées.
    '''
    pos_and_dims = [{'id': item['id'], 'pos': item['pos'], 'dimensions':item['dimensions']} for item in data]
    
    prompt = """You are a 3D Scene Validator and Spatial Coordinator. Your goal is to ensure the simulated objects match the spatial arrangement seen in the REFERENCE image.

            You will receive:
                - Image 1: The REFERENCE image (what the scene must look like).
                - Image 2: The CURRENT SIMULATION (a collage of Perspective, Top, and Side views).
                - A JSON list with the current positions (pos) and dimensions of each object.

            Spatial RULES:
            - Goal: Adjust the X, Y, Z coordinates of the simulated objects so they match the relative positioning, stacking, and alignment shown in the REFERENCE image.
            - Stacking (On Top): For Object A to be "on" Object B, X and Y must be within the space covered by object B. Object A's lowest point must be 0.001 higher than object B's highest point.
            - Collisions: Objects must not logically intersect unless explicitly shown in the reference image. If they overlap in the Top-Down view, they must have different Z-heights to avoid clipping.
            - Ground Plane: No object's lowest point should be below 0.

            Other RULES:
                - ONLY change pos if needed to match the reference image.
                - Maintain the original id for all objects.
                - `valid` is true ONLY if the current simulation perfectly matches the reference image arrangement AND has no illogical collisions.
                - ONLY output the JSON object, nothing else.
                - NO markdown, NO backticks, NO explanations before or after.

            You MUST respond with ONLY this JSON format:
            {
                "valid": boolean,
                "feedback": "Reasoning for changes (e.g., 'Moving mug to be on the left of the laptop to match the reference image')",
                "corrections": [{"id": "string", "pos": [x, y, z]}]
            }
   """

    resultat = ollama.chat(
        model="qwen2.5vl:3b",
        messages=[
            {'role': 'system', 'content': prompt},
            {'role': 'user',
             'content': f"Current Objects and positions: {json.dumps(pos_and_dims)}\nReview the reference image (first) and the current simulation (second).",
             'images': [user_image_path, scene_image_path]} 
        ]
    )
    
    clean = clean_reponse(resultat['message']['content'])
    try:
        resultat = json.loads(clean)
    except json.JSONDecodeError:
        print("json invalide pour etapes_validation")
        return {"valid": False, "feedback": "json invalide"}
        
    if 'corrections' in resultat:
        corrections = {c['id']: c['pos'] for c in resultat['corrections']}
        data = correct_list(data, corrections, 'pos')
        
    return resultat, data