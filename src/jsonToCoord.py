import json
import os
import xml.etree.ElementTree as ET
import random
import trimesh


'''
Des liens utiles:
https://wiki.ros.org/urdf/XML/link
https://genesis-world.readthedocs.io/en/latest/user_guide/getting_started/conventions.html
'''


def readJSON(path):
    '''
    Lit le JSON et extrait les informations en liste d'items et leur relations

    :param path: le path du fichier JSON
    :return items: la liste de dicts d'item contenant id et urdf
    :return relations: la liste de dicts de relations (type, subject, item)
    '''
    with open(path, 'r') as file:
        data = json.load(file)
    items = data.get('objects', [])
    relations = data.get('relations', [])

    return items, relations


def addMass(filepath): #TODO: c'est une tentative de regler le pb des items de la librairie partnet partial qui ne veulent pas s'afficher sur genesis; ne marche pas pour l'instant.
    '''
    Ajoute une masse à l'item urdf pour qu'il soit solide dans la simulation. Ajoute aussi la résistance
    à la rotation (distribution de la masse) #TODO: valeurs plus réalistes

    :param filepath: le path pour le file urdf original
    :return patched_filepath: le path pour le file urdf modifié avec la masse
    '''
    tree = ET.parse(filepath) #lecture du fichier urdf en xml
    root = tree.getroot()

    for link in root.findall('link'):
        for collision in link.findall('collision'):
            link.remove(collision)

        inertial = link.find('inertial')
        if inertial is None:
            inertial = ET.SubElement(link, 'inertial')
            mass = ET.SubElement(inertial, 'mass')
            mass.set('value', '1.0') 
            mass_inertia = ET.SubElement(inertial, 'inertia')
            mass_inertia.set('ixx', '0.1')
            mass_inertia.set('ixy', '0.0')
            mass_inertia.set('ixz', '0.0')
            mass_inertia.set('iyy', '0.1')
            mass_inertia.set('iyz', '0.0')
            mass_inertia.set('izz', '0.1')
    patched_filepath = filepath.replace('.urdf', '_patched.urdf')
    tree.write(patched_filepath)
    return patched_filepath
    

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


    # si c'est un dossier on cherche un fichier qui existe
    if os.path.isdir(base):
        for name in ["mobility.urdf", "kinbody.xml", "textured.obj", "nontextured.stl", "nontextured.ply"]:
            path = os.path.join(base, name)
            if os.path.exists(path):
                return path

        raise FileNotFoundError(f"Aucun fichier exploitable trouvé dans {base}")

    return base



def getDimensions(item):
    '''
    Extrait les dimensions de l'item URDF, qui sont dans '<geometry>'

    :param filepath: le path pour le file urdf
    :return: dimensions de l'item
    '''

    tree = ET.parse(item['path']) #lecture du fichier urdf en xml
    root = tree.getroot()

    for geometry in root.iter('geometry'):
        box= geometry.find('box')
        if box is not None:
            size = box.attrib['size'].split()
            item['dimensions'] = (float(size[0]),float(size[1]), float(size[2]))
            return item
        
        cylinder= geometry.find('cylinder')
        if cylinder is not None:
            r = float(cylinder.attrib['radius'])
            length = float(cylinder.attrib['length'])
            item['dimensions'] = (r*2, r*2, length)
            return item
        
        sphere= geometry.find('sphere')
        if sphere is not None:
            r = float(sphere.attrib['radius'])
            item['dimensions'] = (r*2, r*2, r*2)
            return item
        
        mesh_tag = geometry.find('mesh') #quand les formes sont plus complexes c'est généralement mesh qui est utilisé
        if mesh_tag is not None:
            directory = os.path.dirname(item['path'])
            path_mesh = os.path.join(directory, mesh_tag.attrib['filename'])
            mesh = trimesh.load(path_mesh, force='mesh') #force='mesh' est pour ne pas avoir de scene, seulement un mesh unique
            bounds = mesh.bounding_box.extents
            item['dimensions'] = (float(bounds[0]),float(bounds[1]),float(bounds[2]))
            return item

    print("Dimensions non trouvées") #TODO: faire une meilleure erreur
    item['dimensions'] = (0.1,0.1,0.1)
    return item


def initPosAndQuat(items):
    '''
    Initialise les positions et orientations des objets.
    Donne des orientations et positions de base à tous les items, qui seront modifiées ensuite en fonction des relations.

    :param items: les items
    :return: les items mais avec des positions et orientations de base.
    '''
    for item in items:
        item = getDimensions(item)
        (_, _, height) = item['dimensions']
        item['pos'] = (0,0,0.01 + height/2) #height/2 car les items sont placés par leur centre 
        item['quat'] = (0,0,0,1) #pas de rotation
    return items


def getRoot(items):
    '''
    Trouve l'item root et le met dans placed_items.
    
    :param items: les items
    :return: les items placés qui ne contient que le root pour l'instant
    '''
    placed_items = set()

    for item in items:
        if item.get('root') is True:
            placed_items.add(item['id'])

    if not placed_items:
        raise ValueError("Aucun objets trouvés smh")

    return placed_items


def simplifyRelations(relations):
    '''
    Transforme les relations 'under' en relation 'on' en échangeant le sujet et l'objet pour garder une logique par rapport au processus de placement.

    :param relations: les relations
    :return: les relations avec des 'on' au lieu des 'under'
    '''
    for rel in relations:
        if rel['type'] == 'under':
            rel['subject'], rel['object'] = rel['object'], rel['subject']
            rel['type'] = 'on'
    return relations


def generateCoord(items, relations):
    '''
    Adapte les coordonnees x,y,z des items en fonction des relations.

    :param items: liste de dict d'items
    :param relations: les relations entre les items
    :return: items, les items avec les bonnes coordonnées et les bonnes 
    '''

    items_dict = {item['id']: item for item in items} #pour pouvoir acceder aux differents items plus facilement

    items = initPosAndQuat(items)
    placed_items = getRoot(items)
    
    relations = simplifyRelations(relations)

    reste = relations.copy() #les relations non effectuées
    while reste:
        progression = False
        for rel in reste[:]:
            item_id = rel['object'] #l'objet comparé au sujet, mais c'est dangereux d'utiliser object en python vu que ça existe déjà
            subject_id = rel['subject']
            item = items_dict[item_id]
            subject = items_dict[subject_id]
            if item_id not in placed_items:
                continue
            else:
                item = getDimensions(item)
                (width, depth, height) = item['dimensions']
                (x,y,z) = item['pos']
                subject = getDimensions(subject)
                (subject_w, subject_d, subject_h) = subject['dimensions']
                (subject_x, subject_y, subject_z) = subject['pos']
                if rel['type'] == 'on':
                    subject_x += random.uniform(x - width/2 + subject_w/2, x + width/2 - subject_w/2) #prise en compte des dims du sujet pour ne pas etre trop au bord
                    subject_y += random.uniform(y - depth/2 + subject_d/2, y + depth/2 - subject_d/2)
                    subject_z += z + height/2
                #TODO: pour les elifs suivants: changer le x ou y aussi avec random en fonction des dimensions de l'item?
                #TODO: rendre ce code plus efficace et modulable
                elif rel['type'] == 'in_front_of': #TODO: deal avec les choses qui dépassent des dimensions comme la poignée
                    subject_x += random.uniform(x + width/2 + subject_w/2, x + width + subject_w/2)
                    subject_z = z
                elif rel['type'] == 'behind': # TODO: pb: la handle du mug. on laisse à la validation vlm et les quaternions ou pas? 
                    #subject_x += random.uniform(x - width/2 - subject_w/2, x - width - subject_w/2)
                    subject_x += random.uniform(x - width/2 - subject_w , x - width - subject_w/2) #temp fix
                    subject_z = z
                elif rel['type'] == 'right_of':
                    subject_y += random.uniform(y + depth/2 + subject_d/2, y + depth + subject_d/2)
                    subject_z = z
                elif rel['type'] == 'left_of':
                    subject_y += random.uniform(y - depth/2 - subject_d/2, y - depth - subject_d/2)
                    subject_z = z
                elif rel['type'] == 'against': #TODO
                    pass
                subject['pos'] = (subject_x, subject_y, subject_z)
                placed_items.add(subject_id)
                reste.remove(rel)
                progression = True
        if not progression:
            raise ValueError(f"Impossible de placer les relations restantes : {reste}")
    return items


def buildScene(items, relations):
    '''
    Ajoute à une liste de dictionnaires (un dict par item), toutes les infos nécessaies à la simulation, donc path et pos
    '''
    for item in items:
        item['path'] = getFilePath(item)
    items = generateCoord(items,relations)
    return items