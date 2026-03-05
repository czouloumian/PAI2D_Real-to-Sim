import json
import os
import xml.etree.ElementTree as ET
import random


def readJSON(path):
    '''
    Lit le JSON et extrait les informations en liste d'objets et leur relations

    :param path: le path du fichier JSON
    :return objets: la liste de dicts d'objet contenant id et urdf
    :return relations: la liste de dicts de relations (type, subject, objet)
    '''
    with open(path, 'r') as file:
        data = json.load(file)
    objets = data.get('Objets', [])
    relations = data.get('Relations', [])

    return objets, relations


def addMass(filepath): #TODO: c'est une tentative de regler le pb des objets de la librairie partnet partial qui ne veulent pas s'afficher sur genesis; ne marche pas pour l'instant.
    '''
    Ajoute une masse à l'objet urdf pour qu'il soit solide dans la simulation. Ajoute aussi la résistance
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
    

def getFilePath(objet):
    '''
    Donne le path pour l'objet URDF.

    :param objet: le dictionnaire d'objet avec id et urdf
    :return path: le path pour l'objet
    '''
    objets_folder = os.path.join(os.path.dirname(__file__),'..', 'objets')
    path = os.path.join(objets_folder, objet['urdf'])
    if not os.path.exists(path):
        raise FileNotFoundError(f"Pour {objet['id']}, le fichier {objet['urdf']} est introuvable.")
    #path = addMass(path)
        
    return path


def getDimensions(objet):
    '''
    Extrait les dimensions de l'objet URDF, qui sont dans '<geometry>'

    :param filepath: le path pour le file urdf
    :return: dimensions de l'objet
    '''

    tree = ET.parse(objet['path']) #lecture du fichier urdf en xml
    root = tree.getroot()
    
    for geometry in root.iter('geometry'):
        box= geometry.find('box')
        if box is not None:
            size = box.attrib['size'].split()
            objet['dimensions'] = (float(size[0]),float(size[1]), float(size[2]))
            return objet

    #TODO: regarder s'il y a d'autres choses possible que box
    print("Dimensions non trouvées")
    objet['dimensions'] = (0.1,0.1,0.1)
    return objet


def getRoot(objects):
    '''
    Trouve l'objet root et lui donnes les dimensions de base; le met dans placed_objects

    :param objects: les objets
    :return: objets et les objets placés qui ne contient que le root pour l'instant
    '''
    placed_objects = set() #retiens les objets placés

    for obj in objects:
        obj = getDimensions(obj)
        (width, depth, height) = obj['dimensions']
        if obj['root'] == "true":
            obj['pos'] = (0,0,0.01 + height/2) #height/2 car les objets sont placés par leur centre 
            placed_objects.add(obj['id'])

    return objects, placed_objects


def generateCoord(objects, relations):
    '''
    Genere les coordonnees x,y,z de l'objet en fonction de sa relation avec un autre objet.
    '''
    #on, under, next_to, in

    objects_dict = {obj['id']: obj for obj in objects} #pour pouvoir acceder aux differents objets plus facilement

    objects, placed_objects = getRoot(objects)

    #TODO: transformer les under en on en echangeant objet et sujet

    reste = relations.copy() #les relations non effectuées
    while reste:
        for rel in reste:
            object_id = rel['object']
            subject_id = rel['subject']
            object = objects_dict[object_id]
            subject = objects_dict[subject_id]
            if object_id not in placed_objects:
                continue
            else:
                object = getDimensions(object)
                (width, depth, height) = object['dimensions']
                (x,y,z) = object['pos']
                if rel['type'] == 'on': #TODO: prendre en compte les dimensions du sujet pour ne pas etre trop au bord
                    subject_x = random.uniform(x - width/2, x + width/2)
                    subject_y = random.uniform(y - depth/2, y + depth/2)
                    subject_z = z + height + 0.01
                elif rel['type'] == 'nextTo':
                    subject_x = random.uniform(x + width/2, x + width*2) #TODO: revoir ces ranges
                    subject_y = random.uniform(y + depth/2, y + depth*2)
                    subject_z = z
                subject['pos'] = (subject_x, subject_y, subject_z)
                placed_objects.add(subject_id)
                reste.remove(rel)
    return objects


def createObjectList(objets, relations):
    '''
    Ajoute à une liste de dictionnaires (un dict par objet), toutes les infos nécessaies à la simulation, donc path et pos
    '''
    for obj in objets:
        obj['path'] = getFilePath(obj)
    objets = generateCoord(objets,relations)
    return objets