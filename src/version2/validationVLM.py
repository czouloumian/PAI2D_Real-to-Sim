
import os
import ollama
import json
import re
import xml.etree.ElementTree as ET
import trimesh
import shutil
from datetime import datetime
from jsonToSim import create_scene_validation

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

def create_run_dir():
    '''un dossier pour chaque run'''
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'runs', timestamp)
    os.makedirs(run_dir, exist_ok=True)
    return run_dir


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

def boucle_vlm(user_prompt, jsonFile, image_path, max_iter=3):

    run_dir = create_run_dir()
    history = []

    for iter in range(max_iter):
        with open(jsonFile, 'r') as file:
            data = json.load(file)
        itemsList = data.get('objets', [])
        itemsList = getOriginalDimensions(itemsList)
        image_path = create_scene_validation(itemsList, fixed=True)
        shutil.copy(image_path, os.path.join(run_dir, f"iteration_sol_{iter}_image.png"))
        with open(os.path.join(run_dir, f'iter_sol_{iter}_scene.json'), 'w') as f:
            json.dump(data, f)

        res = verif_fixage_sol(jsonFile, image_path)

        history.append({
            'iteration': iter,
            'feedback': res.get('feedback', ''),
            'valid': res.get('valid', False)
        })
        with open(os.path.join(run_dir, 'history.json'), 'w') as f:
            json.dump(history, f, indent=4)

        if res.get('valid'):
            print("FIXAGE VALIDE")
            break
        else:
            if "new_scene" in res:
                with open(jsonFile, 'w') as file:
                    json.dump({'objets': res['new_scene']['objets']}, file) 
            else:
                if 'objets' in res:
                    items = res['objets']
                    with open(jsonFile, 'w') as file:
                        json.dump({'objets': items}, file)
                else:
                    print("le llm n'a pas donné de nouvelle scene")
                    continue
    print("boucle fixage terminee")


    for iter in range(max_iter):
        print("START DE LA BOUCLE ORIENTATION, ITERATION ", iter)
        with open(jsonFile, 'r') as file:
            data = json.load(file)
        itemsList = data.get('objets', [])
        itemsList = getOriginalDimensions(itemsList)
        image_path = create_scene_validation(itemsList, fixed=True)
        shutil.copy(image_path, os.path.join(run_dir, f"iteration_orientation_{iter}_image.png"))
        with open(os.path.join(run_dir, f'iter_orientation_{iter}_scene.json'), 'w') as f:
            json.dump(data, f)
        res = verif_orientation(jsonFile, image_path, user_prompt)
        history.append({
            'iteration': iter,
            'feedback': res.get('feedback', ''),
            'valid': res.get('valid', False)
        })
        with open(os.path.join(run_dir, 'history.json'), 'w') as f:
            json.dump(history, f, indent=4)
        if res.get('valid'):
            print("ORIENTATION VALIDE")
            break
        else:
            if "new_scene" in res:
                with open(jsonFile, 'w') as file:
                    json.dump({'objets': res['new_scene']['objets']}, file) 
            else:
                if 'objets' in res:
                    items = res['objets']
                    with open(jsonFile, 'w') as file:
                        json.dump({'objets': items}, file)
                else:
                    print("le llm n'a pas donné de nouvelle scene")
                    continue
    print("boucle orientation terminee")


    for i in range(max_iter):
        print("START DE LA BOUCLE ETAPES, ITERATION ", i)
        with open(jsonFile, 'r') as file:
            data = json.load(file)
        itemsList = data.get('objets', [])
        #itemsList = getFilePath(itemsList) #TODO: a changer plus tard
        itemsList = getOriginalDimensions(itemsList)

        has_overlap = checkOverlap(itemsList)
        collision_feedback = "overlap detected" if has_overlap else "no overlap"
        image_path = create_scene_validation(itemsList, fixed=True)

        shutil.copy(image_path, os.path.join(run_dir, f"iteration_boucle_{iter}_image.png"))
        with open(os.path.join(run_dir, f'iter_boucle_{iter}_scene.json'), 'w') as f:
            json.dump(data, f)

        res = etapes_validation(user_prompt,jsonFile,image_path, collision_feedback)

        history.append({
            'iteration': i,
            'feedback': res.get('feedback', ''),
            'valid': res.get('valid', False)
        })
        with open(os.path.join(run_dir, 'history.json'), 'w') as f:
            json.dump(history, f, indent=4)

        if res.get("valid")==True:
            print("scene validée")
            return res
        else:
            print("echec: ", res.get("feedback"))
            if "new_scene" in res:
                with open(jsonFile, 'w') as file:
                    json.dump({'objets': res['new_scene']['objets']}, file) 
            else:
                if 'objets' in res:
                    items = res['objets']
                    with open(jsonFile, 'w') as file:
                        json.dump({'objets': items}, file)
                else:
                    print("le llm n'a pas donné de nouvelle scene")
                    continue
        print(f"itération {i+1}: {res}")
    return res


def verif_fixage_sol(jsonFile, image_path):
    with open(jsonFile, 'r') as file:
        data = json.load(file)
    z_and_dims = [
        {
            'id': item['id'], 
            'z': item['pos'][2],
            'height': item['dimensions'][2] if 'dimensions' in item else None,
            'suggested_min_z': round(item['dimensions'][2] / 2 + 0.01, 4) if 'dimensions' in item else None
        } 
        for item in data['objets']
    ]
    prompt = """You are a scene corrector. Your task is to verify if the objects in the scene are properly placed above the ground plane. If any object is clipping into it, correct its position by adjusting only the Z coordinate.
            You should augment the z coordinate until the object is slightly above the ground plane. The object should NOT touch the ground plane, it should be slightly above it, around 0.01m. If the object is already above the ground plane, do not change its position.
            You will receive:
                - The current scene's object's z coordinates, their dimensions and the suggested minimum z to be above the ground plane
                - a collage containing FOUR images of the same scene:
                    1. PERSPECTIVE VIEW: General context.
                    2. TOP-DOWN VIEW: Best for X, Y coordinates and checking if objects are side-by-side.
                    3. SIDE VIEW: Best for Z coordinate (height) to check if objects are at the right height.
                    4. SECOND SIDE VIEW: Best for checking if objects are properly placed below the ground plane.

                RULES:
                - THERE SHOULD BE NO OBJECTS CLIPPING INTO THE GROUND PLANE. If there are, 'valid' is FALSE and you MUST provide corrected Z values for those objects.
                - ONLY output the JSON object, nothing else
                - NO markdown, NO backticks, NO explanations before or after
                - NEVER rename keys, only change values
                - Always use double quotes for keys and strings
                - DO NOT change 'id'.
                - If valid is true, new_scene can be identical to the input
                - There should NOT be ANY collisions
                - If objects overlap, 'valid' is FALSE.
                - DO NOT lower an object if you don't see space between the object and the ground
                - There should be AT LEAST 0.01m between the lowest point of the object and the ground plane. If there is less,the scene is NOT VALID, increase the Z coordinate until there is at least 0.01m of space.
                - The suggested minimum z is calculated as the height of the object / 2 + 0.01m, but you can adjust it if you think it is necessary based on the images. The important thing is that there should be no clipping and at least 0.01m of space.
                    
            You MUST respond with ONLY this JSON format:
            {
                "valid": false,
                "feedback": "mug is clipping into ground",
                "corrections": [
                    {"id": "mug", "z": 0.01},
                    {"id": "table", "z": 0.375}
                ]
            }
            """
    resultat = ollama.chat(
        model="llama3.2-vision",
        messages=[
            {'role': 'system', 'content': prompt},
            {'role': 'user', 
             'content': f"Objects and their current Z: {json.dumps(z_and_dims)}",
             'images': [image_path]}
        ]
    )
    clean = clean_reponse(resultat['message']['content'])
    try:
        resultat = json.loads(clean)
    except json.JSONDecodeError:
        print("json invalide pour verif fixage sol")
    if 'corrections' in resultat:
        corrections = {}
        for c in resultat['corrections']:
            if 'z' in c:
                corrections[c['id']] = c['z']
            elif 'pos' in c and len(c['pos']) == 3:
                corrections[c['id']] = c['pos'][2]
        for item in data['objets']:
            if item['id'] in corrections:
                old_z = item['pos'][2]
                new_z = corrections[item['id']]
                item['pos'][2] = new_z
                print(f"Z corrigé pour {item['id']}: {old_z:.3f} → {new_z:.3f}")
    
        with open(jsonFile, 'w') as file:
            json.dump(data, file, indent=4)
    return resultat


def verif_orientation(jsonFile, image_path, original_prompt):
    with open(jsonFile, 'r') as file:
        data = json.load(file)
    quat_only = [{'id': item['id'], 'quat': item.get('quat', [0,0,0,1])} 
                 for item in data['objets']]
    
    prompt = """You are an orientation corrector for 3D scenes.
    Your task is to check if objects are oriented correctly based on the prompt and the image.
    
    COORDINATE SYSTEM:
    - X axis: left/right
    - Y axis: forward/backward  
    - Z axis: up/down
    - Quaternion format: [x, y, z, w] where [0,0,0,1] means no rotation
    
    Common useful rotations:
    - No rotation: [0, 0, 0, 1]
    - 90° around Z (turn left): [0, 0, 0.707, 0.707]
    - 180° around Z (face opposite): [0, 0, 1, 0]
    - 90° around X (tip forward): [0.707, 0, 0, 0.707]
    - Lying on side: [0.707, 0, 0, 0.707]
    
    You will receive:
    - The original prompt
    - The current quaternions for each object
    - A collage of FOUR views: perspective, top, side, side2
    
    RULES:
    - ONLY change quat if an object is clearly wrongly oriented
    - Object should be upright unless overwise specified in the prompt.
    - DO NOT change quat if orientation looks correct
    - valid is true only if ALL objects have correct orientation
    - Always use a valid unit quaternion (norm must equal 1)
    
    You MUST respond with ONLY this JSON format:
    {
        "valid": true,
        "feedback": "all objects correctly oriented",
        "corrections": [
            {"id": "mug", "quat": [0, 0, 0, 1]},
            {"id": "banana", "quat": [0.707, 0, 0, 0.707]}
        ]
    }"""
    resultat = ollama.chat(
        model="llama3.2-vision",
        messages=[
            {'role': 'system', 'content': prompt},
            {'role': 'user',
             'content': f"Prompt: {original_prompt}\nCurrent orientations: {json.dumps(quat_only)}",
             'images': [image_path]}
        ]
    )
    clean = clean_reponse(resultat['message']['content'])
    try:
        resultat = json.loads(clean)
    except json.JSONDecodeError:
        print("json invalide pour verif orientation")
        return {"valid": True}
    if 'corrections' in resultat:
        corrections = {c['id']: c['quat'] for c in resultat['corrections']}
        for item in data['objets']:
            if item['id'] in corrections:
                old_quat = item.get('quat', [0,0,0,1])
                new_quat = corrections[item['id']]
                norm = sum(x**2 for x in new_quat) ** 0.5
                if norm < 0.01: #ignore parce a=que pas valide
                    continue
                item['quat'] = [x/norm for x in new_quat]
                print(f"Quat corrigé pour {item['id']}: {old_quat} → {item['quat']}")
        with open(jsonFile, 'w') as file:
            json.dump(data, file, indent=4)
    return resultat


def etapes_validation(original_prompt, jsonFile, image_path, collision_feedback=None):
    with open(jsonFile, 'r') as file:
        data = json.load(file)
    pos_and_dims = [{'id': item['id'], 'pos': item['pos']} for item in data['objets']]
    z_and_dims = [{'id': item['id'], 'pos': item['pos'],'dimensions': item['dimensions'] if 'dimensions' in item else None} for item in data['objets']]
    prompt = """You are a scene validator.
    Check if the scene matches the prompt and if there are collisions.
    Return corrected positions only.

    You will receive:
        - The current scene as a JSON object
        - The position and dimensions of each object
        - a collage containing THREE images of the same scene:
            1. PERSPECTIVE VIEW: General context.
            2. TOP-DOWN VIEW: Best for X, Y coordinates and checking if objects are side-by-side.
            3. SIDE VIEW: Best for Z coordinate (height) to check if objects are at the right height.
    
    You MUST respond with ONLY this JSON format:
    {
        "valid": true,
        "feedback": "scene matches prompt",
        "corrections": [
            {"id": "mug", "pos": [0.3, 0.0, 0.5]},
            {"id": "table", "pos": [0.0, 0.0, 0.375]}
        ]
    }

    RULES:
    - ONLY change pos if needed
    - valid is true only if scene matches prompt AND no collisions
    - DO NOT have objects that clip into the ground
    - For objects to be on top of another, you have to adjust the x and y so that they are similar, and the z of the object on top for it to be higher than the height of the other object.
    """

    resultat = ollama.chat(
        model="llama3.2-vision",
        messages=[
            {'role': 'system', 'content': prompt},
            {'role': 'user',
             'content': f"Prompt: {original_prompt}\nObjects and positions: {json.dumps(pos_and_dims)}\nCollision report: {collision_feedback}",
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
        for item in data['objets']:
            if item['id'] in corrections:
                old_pos = item['pos']
                item['pos'] = corrections[item['id']]
                print(f"Pos corrigée pour {item['id']}: {old_pos} → {item['pos']}")
        
        with open(jsonFile, 'w') as file:
            json.dump(data, file, indent=4)
    return resultat



def etapes_validation_old(original_prompt, jsonFile, image_path, collision_feedback=None):
    with open(jsonFile, 'r') as file:
        data = json.load(file)
    pos_only = [{'id': item['id'], 'pos': item['pos']} for item in data['objets']]
    #collisions
    prompt1 = """You are a collision corrector. If the collision feedback states that there is collision, correct the scene so there is no collision anymore. Only correct the posistion, "pos".

                You will receive:
                    - The current scene as a JSON object
                    - a collage containing THREE images of the same scene:
                        1. PERSPECTIVE VIEW: General context.
                        2. TOP-DOWN VIEW: Best for X, Y coordinates and checking if objects are side-by-side.
                        3. SIDE VIEW: Best for Z coordinate (height) to check if objects are at the right height.

                RULES:
                    - ONLY output the JSON object, nothing else
                    - NO markdown, NO backticks, NO explanations before or after
                    - NEVER rename keys, only change values
                    - Always use double quotes for keys and strings
                    - ALWAYS keep the same "id" and "urdf" values as the input JSON
                    - Keep the same number of objects as the input JSON, do not add or remove objects
                    - ONLY change "pos" values to fix the scene
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
                {'role': 'user','content': f"Current JSON scene: {json.dumps(data)}\nCollision report: {collision_feedback}",'images': [image_path]}])
    clean = clean_reponse(resultat1['message']['content'])
    skip = False
    try:
        resultat1 = json.loads(clean)
    except json.JSONDecodeError:
        skip = True
        print("json invalide pour la correction de collision")
    if skip == False and not resultat1.get('valid'):
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
                    - NEVER rename keys, only change values
                    - NO markdown, NO backticks, NO explanations before or after
                    - Always use double quotes for keys and strings
                    - ALWAYS keep the same "id" and "urdf" values as the input JSON
                    - Keep the same number of objects as the input JSON, do not add or remove objects
                    - ONLY change "pos" values to fix the scene so it matches the prompt.
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
                {'role': 'user','content': f"Check and correct if the generated scene {json.dumps(data)} is accurate to the prompt {original_prompt}.",'images': [image_path]}])
    clean = clean_reponse(resultat2['message']['content'])
    try:
        resultat2 = json.loads(clean)
    except json.JSONDecodeError:
        print("json invalide pour la correction de collision")
    return resultat2