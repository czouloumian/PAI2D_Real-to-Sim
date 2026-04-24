
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
    shutil.copy(image_path, os.path.join(run_dir, f"iteration_{iter}_image.png"))
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


def boucle_vlm(user_prompt, jsonFile, max_iter=3):

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
            'phase': "semantique",
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


def validation_physique(objetsList): #TODO: résoudre aussi les collisions entre les objets
    steps = 150
    dt = 0.01
    corrected_objects = copy.deepcopy(objetsList)
    gs.init(backend=gs.cpu)
    scene = gs.Scene(show_viewer=False, sim_options=gs.options.SimOptions(dt=dt))
    scene.add_entity(gs.morphs.Plane()) #TODO: regarder les textures pour voir si ça peut améliorer les choses de mettre des bounds!!!!! d
    #donner les x et y bounds au llm. dire de ne pas s'approcher trop pres du bord de la table. it slays
    cameras = {
        "perspective":scene.add_camera(res=(640, 480), pos=(3.5, 0.0, 2.5), lookat=(0, 0, 0.5), fov=30),
        "top":scene.add_camera(res=(640, 480), pos=(0.0, 0.0, 4.0), lookat=(0, 0, 0),   fov=40),
        "side":scene.add_camera(res=(640, 480), pos=(0.0, 3.5, 1.0), lookat=(0, 0, 0.5), fov=30),
        "side2": scene.add_camera(res=(640, 480),pos=(3.5, 0.0, 0.5),lookat=(0, 0, 0.5),fov=30)
    }
    entities = []
    for obj in corrected_objects:
        ent = scene.add_entity(
            gs.morphs.URDF(
                file=obj['path'],
                pos=tuple(obj['pos']),
                quat=tuple(obj.get('quat', [0.0, 1.0, 1.0, 0.0])),
                scale=obj.get('scale', 1.0),
                fixed=False 
            ),
            material=gs.materials.Rigid(rho=1000)
        )
        entities.append(ent)
    scene.build()
    for i, ent in enumerate(entities):
        aabb_min, aabb_max = ent.get_AABB() #get aabb permet de trouver le vrai plus petit point de l'objet
        z_min = float(aabb_min[2])
        if z_min < 0.0: #ça veut dire que l'objet est partiellement sous le sol
            correction = abs(z_min) + 0.001
            corrected_objects[i]['pos'][2] += correction
            current_pos = ent.get_pos()
            ent.set_pos([current_pos[0], current_pos[1], current_pos[2] + correction])

    #TODO: on pourrait utiliser aabb_max pour les relations "on"

    z_init = [float(ent.get_pos()[2]) for ent in entities]
    for _ in range(steps):
        scene.step()
    z_final = [float(ent.get_pos()[2]) for ent in entities]
    for i, obj in enumerate(corrected_objects):
        delta_z = z_final[i] - z_init[i]
        v_z = delta_z / (steps * dt)
        if v_z > 0.5: #l'objet a été expulsé vers le haut, donc il était trop bas
            obj['pos'][2] += 0.05 
        elif delta_z < -0.001: #l'onbjet est tombe donc il etait trop haut
            obj['pos'][2] = z_final[i] #on met la hauteyr finale là où l'objet est retombé
            # final_quat = ent.get_quat()
            # obj['quat'] = [float(q) for q in final_quat]
  
    image_paths = []
    base_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'images')
    os.makedirs(base_dir, exist_ok=True)

    views = ["perspective", "top", "side", "side2"]
    images = []

    try: 
        font = ImageFont.truetype("arial.ttf", 25)
    except: 
        font = ImageFont.load_default()
    
    for name in views:
        rgb, _, _, _ = cameras[name].render(rgb=True)
        images.append(Image.fromarray(rgb))
        draw = ImageDraw.Draw(images[-1])
        draw.text((10, 10), name, font=font, fill=(255, 255, 255))

    widths, heights = zip(*(i.size for i in images))
    total_width = sum(widths)
    max_height = max(heights)

    collage = Image.new('RGB', (total_width, max_height))

    x_offset = 0
    for im in images:
        collage.paste(im, (x_offset, 0))
        x_offset += im.size[0]

    path_collage = os.path.abspath("images/collage_validation.png")
    collage.save(path_collage)

    gs.destroy()
    return path_collage, corrected_objects