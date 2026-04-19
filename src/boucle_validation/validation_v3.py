
import os
import ollama
import json
import re
import shutil
from datetime import datetime
from .jsonToSim import create_scene_validation
from PIL import Image

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


def boucle_vlm(user_img, jsonFile, max_iter=5):

    run_dir = create_run_dir()
    history = []
    #on met l'image donnée par l'user dans la première ligne du collage
    im_width, im_height = zip(*(user_img.size))
    collage = Image.new('RGB', (im_width, im_height))
    collage.paste(user_img, (0,0))

    for iter in range(max_iter):
        with open(jsonFile, 'r') as file:
            data = json.load(file)
        itemsList = data.get('objets', [])
        image_path = create_scene_validation(itemsList, fixed=True)
        shutil.copy(image_path, os.path.join(run_dir, f"image_iteration_{iter}_image.png"))
        with open(os.path.join(run_dir, f'iter_sol_{iter}_scene.json'), 'w') as f:
            json.dump(data, f)

        # TODO: faire le collage avec première image du collage étant la photo de l'user, et le reste la current generation. ou alors avoir une ligne dans le collage pour chaque essai??
        #donc TODO: rajouter les images de la génération en tant que nouvelle colonne à l'image à chaque fois
        path_collage = os.path.abspath("images/collage_validation.png")
        collage.save(path_collage)
        #

        #TODO: pos and dims only??
        pos_and_quat = [{'id': item['id'], 'pos': item['pos'], 'quaternions':item['quat']} for item in data['objets']]

        prompt = """You are a scene corrector. Your task is for the generated scene to look similar to the scene given by the user. For this, you should adjust the JSON file for scene generation.
        
                    You will receive:
                    - the dimensions (x,y,z) and orientations (rotation in quaternions) of all 
                    - a collage containing ONE ORIGINAL image from the user, followed by FOUR images of the same scene:
                        1. PERSPECTIVE VIEW: General context.
                        2. TOP-DOWN VIEW: Best for X, Y coordinates and checking if objects are side-by-side.
                        3. SIDE VIEW: Best for Z coordinate (height) to check if objects are at the right height.
                        4. SECOND SIDE VIEW: Best for checking if objects are properly placed below the ground plane.
                    - a json file containing history of the correction you have already made to 
                        
                You MUST respond with ONLY this JSON format:
                {
                    "valid": false,
                    "feedback": "mug is clipping into ground",
                    "corrections": [
                        {"id": "mug", "pos": [0.3, 0.0, 0.5]},
                        {"id": "table", "pos": 0.[0.0, 0.0, 0.375]}
                    ]
                }
                """
        
        resultat = ollama.chat(model="llama3.2-vision", messages=[{'role': 'system', 'content': prompt},{'role': 'user','content':f"History of runs and corrections: {history}\nCurrent objects positions and orientations: {json.dumps(pos_and_quat)}",'images': [image_path]}])
        clean = clean_reponse(resultat['message']['content'])
        try:
            resultat = json.loads(clean)
        except json.JSONDecodeError:
            print(f"json invalide pour itération {iter}")

        if 'corrections' in resultat:
            corrections = {c['id']: c['pos'] for c in resultat['corrections']}
            for item in data['objets']:
                if item['id'] in corrections:
                    old_pos = item['pos']
                    item['pos'] = corrections[item['id']]
                    print(f"Pos corrigée pour {item['id']}: {old_pos} → {item['pos']}")
            #TODO: corriger les quats désolée j'ai pas eu le temps
            with open(jsonFile, 'w') as file:
                json.dump(data, file, indent=4)
            
                with open(jsonFile, 'w') as file:
                    json.dump(data, file, indent=4)
    

        history.append({
            'iteration': iter,
            'feedback': resultat.get('feedback', ''),
            'correction': resultat.get('correction',''),
            'valid': resultat.get('valid', False)
        })
        with open(os.path.join(run_dir, 'history.json'), 'w') as f:
            json.dump(history, f, indent=4)

        if resultat.get('valid'):
            print("FIXAGE VALIDE")
            break
        else:
            if "new_scene" in resultat:
                with open(jsonFile, 'w') as file:
                    json.dump({'objets': resultat['new_scene']['objets']}, file) 
            else:
                if 'objets' in resultat:
                    items = resultat['objets']
                    with open(jsonFile, 'w') as file:
                        json.dump({'objets': items}, file)
                else:
                    print("le llm n'a pas donné de nouvelle scene")
                    continue

    return resultat
