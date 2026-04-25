import os
import datetime
import json
import shutil
import trimesh


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

def create_run_dir():
    '''un dossier pour chaque run'''
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'runs', timestamp)
    os.makedirs(run_dir, exist_ok=True)
    return run_dir

def save_iteration_scene(image_path, iter, run_dir, itemsList):
    shutil.copy(image_path, os.path.join(run_dir, f"iteration_{iter}.png"))
    with open(os.path.join(run_dir, f'iter_{iter}_scene.json'), 'w') as f:
        json.dump({'objets': itemsList}, f, indent=4)

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


# def getOriginalDimensions(items): #TODO: attention c'est pas la meme que dans v1, à changer
#     '''
#     Extrait les dimensions de l'item URDF, qui sont dans '<geometry>'

#     :param filepath: le path pour le file urdf
#     :return: l'item avec ses dimensions
#     '''
#     for item in items:
#         if item.get('dimensions'):
#             continue
#         else:
#             tree = ET.parse(item['path']) #lecture du fichier urdf en xml
#             root = tree.getroot()

#             for geometry in root.iter('geometry'):
#                 box= geometry.find('box')
#                 cylinder= geometry.find('cylinder')
#                 sphere= geometry.find('sphere')
#                 mesh_tag = geometry.find('mesh') #quand les formes sont plus complexes c'est généralement mesh qui est utilisé
#                 if box is not None:
#                     size = box.attrib['size'].split()
#                     item['dimensions'] = (float(size[0]),float(size[1]), float(size[2]))
#                 elif cylinder is not None:
#                     r = float(cylinder.attrib['radius'])
#                     length = float(cylinder.attrib['length'])
#                     item['dimensions'] = (r*2, r*2, length)
#                 elif sphere is not None:
#                     r = float(sphere.attrib['radius'])
#                     item['dimensions'] = (r*2, r*2, r*2)
#                 elif mesh_tag is not None:
#                     directory = os.path.dirname(item['path'])
#                     path_mesh = os.path.join(directory, mesh_tag.attrib['filename'])
#                     mesh = trimesh.load(path_mesh, force='mesh') #force='mesh' est pour ne pas avoir de scene, seulement un mesh unique
#                     bounds = mesh.bounding_box.extents
#                     item['dimensions'] = (float(bounds[0]),float(bounds[1]),float(bounds[2]))
#                 else:
#                     print("Dimensions non trouvées") #TODO: faire une meilleure erreur
#                     item['dimensions'] = (0.1,0.1,0.1)
#     return items