import os
import xml.etree.ElementTree as ET
import random
from itemSpec import getOriginalDimensions, getFilePath
from jsonParsing import simplifyRelations


'''
Des liens utiles:
https://wiki.ros.org/urdf/XML/link
https://genesis-world.readthedocs.io/en/latest/user_guide/getting_started/conventions.html
'''


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


def initPosAndQuat(items):
    '''
    Initialise les positions et orientations des objets.
    Donne des orientations et positions de base à tous les items, qui seront modifiées ensuite en fonction des relations.

    :param items: les items
    :return: les items mais avec des positions et orientations de base.
    '''
    for item in items:
        item = getOriginalDimensions(item)
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
    placed_items = set() #retiens les items placés

    for item in items:
        if item['root'] == "true":
            placed_items.add(item['id'])

    return placed_items


def changePosFromRel(rel, item, subject):
    '''
    Change les données de positions du sujet en fonction de la relation et de l'item déjà placé

    '''
    processed = True
    item = getOriginalDimensions(item) #TODO maybe will call a diff function once we figure out the scale thing
    (width, depth, height) = item['dimensions']
    (x,y,z) = item['pos']
    subject = getOriginalDimensions(subject)
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
    else:
        pass #TODO: throw an error 

    subject['pos'] = (subject_x, subject_y, subject_z)
    

def changeQuatFromRel():
    '''
    Change l'orientation de l'item en fonction de la relation et du sujet
    '''
    #TODO, et aussi se poser la question de si l'orientation de both le sujet et l'item doivent etre changées, dans le cas de 'facing' par exemple
    pass


def verifyRelations(): #TODO: classer en pos et quaternions possiblement?
    '''
    Vérifie que les relations sont valides, ne prend que les relations qui existent
    '''
    pass


def processRelations(items, relations):
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
        for rel in reste:
            item_id = rel['object'] #l'objet comparé au sujet, mais c'est dangereux d'utiliser object en python vu que ça existe déjà
            subject_id = rel['subject']
            item = items_dict[item_id] #TODO: maybe utiliser une autre nom que item dans ce contexte et seulement ce contexte
            subject = items_dict[subject_id]
            if item_id not in placed_items:
                continue
            else:
                changePosFromRel(rel, item, subject)
                placed_items.add(subject_id)
                reste.remove(rel)
    return items


def buildScene(items, relations): #TODO verif si autres trucs needed
    '''
    Ajoute à une liste de dictionnaires (un dict par item), toutes les infos nécessaies à la simulation, donc path et pos
    '''
    for item in items:
        item['path'] = getFilePath(item)
    items = processRelations(items,relations)
    return items