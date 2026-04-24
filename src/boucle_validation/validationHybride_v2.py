
import os
import ollama
import json
import re
import xml.etree.ElementTree as ET
import trimesh
import shutil
from datetime import datetime
from jsonToSim import create_scene_validation, validation_physique
import json
from scipy.spatial.transform import Rotation as R
import copy
import genesis as gs
from PIL import Image, ImageDraw, ImageFont


def getFilePath(item):
    '''
    Donne le path pour l'item URDF.

    :param item: le dictionnaire d'item avec id et urdf
    :return path: le path pour l'item
    '''
    items_folder = os.path.join(os.path.dirname(__file__),'..', 'objets')
    base = os.path.join(items_folder, item['urdf'])
    if not os.path.exists(base):
        raise FileNotFoundError(f"Pour {item['id']}, le fichier {item['urdf']} est introuvable.")
    #path = addMass(path)

    #TODO: question: pourquoi on cherche d'autres fichiers que mobility.urdf?
    # si c'est un dossier on cherche un fichier qui existe
    if os.path.isdir(base):
        for name in ["mobility.urdf", "kinbody.xml", "textured.obj", "nontextured.stl", "nontextured.ply"]:
            path = os.path.join(base, name)
            if os.path.exists(path):
                return path

        raise FileNotFoundError(f"Aucun fichier exploitable trouvé dans {base}")

    return base

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

def create_run_dir():
    '''un dossier pour chaque run'''
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'runs', timestamp)
    os.makedirs(run_dir, exist_ok=True)
    return run_dir


def save_iteration_scene(image_path, iter, run_dir, itemsList):
    shutil.copy(image_path, os.path.join(run_dir, f"iteration_{iter}_image_v2.png"))
    with open(os.path.join(run_dir, f'iter_{iter}_scene.json'), 'w') as f:
        json.dump({'objets': itemsList}, f, indent=4)


def correct_json(jsonFile, corrections, field):
    with open(jsonFile, 'r') as file:
        data = json.load(file)
    existing_id = {item['id'] for item in data['objets']}
    for c_id in corrections.keys():
        if c_id not in existing_id:
            print(f"ATTENTION: l'ID {c_id} n'est pas dans le JSON, skipping correction.")
    for item in data['objets']:
        if item['id'] in corrections:
            old_value = item[field]
            item[field] = corrections[item['id']]
            print(f"CORRECTION: {field} corrigée pour {item['id']}: {old_value} → {item[field]}")
    with open(jsonFile, 'w') as file:
        json.dump(data, file, indent=4)


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
    resultat = re.sub(r'```', '', resultat)
    start = resultat.find('{')
    end = resultat.rfind('}') + 1
    if start != -1 and end != 0:
        json_str = resultat[start:end]
        json_str = json_str.replace('True', 'true').replace('False', 'false') 
        return json_str
    return ""


def boucle_vlm_v2(user_prompt, jsonFile, max_iter=3):

    run_dir = create_run_dir()
    history = []

    for iter in range(max_iter):
        
        with open(jsonFile, 'r') as file:
            data = json.load(file)
        itemsList = data.get('objets', [])
        itemsList = getOriginalDimensions(itemsList) #faire ça avec get_aabb?? seems more reliable
        image_path, corrected_objects = validation_physique(itemsList)

        print("CORRECTED OBJETCTS:", corrected_objects)
        #TODO: faut modifier ce qu'on a avec "corrected objects"

        save_iteration_scene(image_path, iter, run_dir, itemsList)
        res, data = etapes_validation(user_prompt,corrected_objects,image_path)
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

        if res.get("valid")==True:
            print("scene validée")
            return data
        else:
            print("echec: ", res.get("feedback"))

    else:
        return data




def etapes_validation(original_prompt, data, image_path):
    #with open(jsonFile, 'r') as file:
    #    data = json.load(file)
    pos_and_dims = [{'id': item['id'], 'pos': item['pos'], 'dimensions':item['dimensions']} for item in data]
    prompt = """ You are a 3D Scene Validator and Spatial Coordinator. Your goal is to ensure objects are logically placed, match the prompt's description, and do not collide (overlap) with each other or the ground.

            You will receive:
                - The current scene as a JSON object
                - The position and dimensions of each object
                - a collage containing THREE images of the same scene:
                    1. PERSPECTIVE VIEW: General context.
                    2. TOP-DOWN VIEW: Best for X, Y coordinates and checking if objects are side-by-side.
                    3. SIDE VIEW: Best for Z coordinate (height) to check if objects are at the right height.
                        
            Spatial RULES:
            - Stacking (On Top): For Object A to be "on" Object B, X and Y must be within the space covered by object B. 
            Object A's lowest point must be 0.001 higher than object B highest point.
            - Next to: for object A to be next to object B, they must have the same height (Z). X and Y may vary depending on if they are at the right, left, in front, behind each other… For example, if the prompt says "Object A is next to Object B", ensure they have the same Z-base but different X or Y.
            - Collisions: Objects must not occupy the same space. If they overlap in the Top-Down view, they must have different Z-heights to avoid clipping. If an object is explicitly inside another, this does not apply. However, meshes still shouldn’t intersect.
            - Ground Plane: No object's lowest point should be below 0.
            - DO NOT throw objects in the air! Objects should be placed on a surface (ground or other objects).

            Other RULES:
                - ONLY change pos if needed
                -  Maintain the original id for all objects.
                - valid is true only if scene matches prompt AND no collisions
                - ONLY output the JSON object, nothing else
                - NO markdown, NO backticks, NO explanations before or after


            You MUST respond with ONLY this JSON format:
            {
                "valid": boolean,
                "feedback":  "Reasoning for changes (e.g., 'Moving mug to be centered on table and fixing ground clipping')",
                "corrections": [{"id": "string", "pos": [x, y, z]}]
            }
   """

    resultat = ollama.chat(
        model="qwen2.5vl:3b",
        messages=[
            {'role': 'system', 'content': prompt},
            {'role': 'user',
             'content': f"Prompt: {original_prompt}\nObjects and positions: {json.dumps(pos_and_dims)}",
             'images': [image_path]}
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
