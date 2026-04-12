import os
import random
from itemSpec import getOriginalDimensions, getFilePath
from jsonParsing import simplifyRelations


'''
Des liens utiles:
https://wiki.ros.org/urdf/XML/link
https://genesis-world.readthedocs.io/en/latest/user_guide/getting_started/conventions.html
'''


def initPosAndQuat(items):
    '''
    Initialise les positions et orientations des objets.
    Donne des orientations et positions de base à tous les items, qui seront modifiées ensuite en fonction des relations.

    :param items: les items
    :return: les items mais avec des positions et orientations de base.
    '''
    for item in items:
        if not item.get('dimensions'):
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
    placed_items = set()

    for item in items:
        if item.get('root') == 'true' or item.get('root') == 'True':
            placed_items.add(item['id'])

    # fallback : si aucun root explicite, utiliser le premier item
    if not placed_items and items:
        print(f"[sceneBuilding] Aucun root explicite, fallback sur '{items[0]['id']}'")
        items[0]['root'] = True
        placed_items.add(items[0]['id'])

    if not placed_items:
        raise ValueError("Aucun objet à placer")

    return placed_items


def changePosFromRel(rel, item, subject):
    '''
    Change les données de positions du sujet en fonction de la relation et de l'item déjà placé

    '''
    if not item.get('dimensions'):
        item = getOriginalDimensions(item)
    (width, depth, height) = item['dimensions']
    (x,y,z) = item['pos']
    if not subject.get('dimensions'):
        subject = getOriginalDimensions(subject)
    (subject_w, subject_d, subject_h) = subject['dimensions']
    (subject_x, subject_y, subject_z) = subject['pos']
    if rel['type'] == 'on':
        subject_x += random.uniform(x - width/2 + subject_w/2, x + width/2 - subject_w/2) #prise en compte des dims du sujet pour ne pas etre trop au bord
        subject_y += random.uniform(y - depth/2 + subject_d/2, y + depth/2 - subject_d/2)
        subject_z += z + height/2
    elif rel['type'] == 'in_front_of':
        subject_x += random.uniform(x + width/2 + subject_w/2, x + width + subject_w/2)
        subject_z = z
    elif rel['type'] == 'behind':
        #subject_x += random.uniform(x - width/2 - subject_w/2, x - width - subject_w/2)
        subject_x += random.uniform(x - width/2 - subject_w , x - width - subject_w/2) #temp fix
        subject_z = z
    elif rel['type'] == 'right_of':
        subject_y += random.uniform(y + depth/2 + subject_d/2, y + depth + subject_d/2)
        subject_z = z
    elif rel['type'] == 'left_of':
        subject_y += random.uniform(y - depth/2 - subject_d/2, y - depth - subject_d/2)
        subject_z = z
    elif rel['type'] == 'against':
        subject_x = x + width/2 + subject_w/2 + 0.01
        subject_y = y
        subject_z = z
    elif rel['type'] == 'inside':
        subject_x = x
        subject_y = y
        subject_z = z 
    elif rel['type'] == 'facing':
        subject_x = x + width/2 + subject_w/2 + random.uniform(0.1, 0.4)
        subject_y = y
        subject_z = z
        qx, qy, qz, qw = subject.get('quat', [0, 0, 0, 1])
        new_quat = [-qy, qx, qw, -qz] 
        subject['quat'] = new_quat
    else:
        print("relation non traitée: ", rel['type'])
    subject['pos'] = (subject_x, subject_y, subject_z)
    


def changeQuatFromTurn(turn, item): #TODO: il va falloir changer le code pour que ça trouve turn dans le json et tout
    '''
    Change les données d'orientation du sujet
    '''

    current = item.get('quat', [0, 0, 0, 1])
    rotations = {
        'turn_left':    [0, 0, 0.707, 0.707],# 90 autour de z
        'turn_right':   [0, 0, -0.707, 0.707],# -90° autour de z
        'turn_back':    [0, 0, 1, 0],# 180° autour de z
        'tip_forward':  [0.707, 0, 0, 0.707],# 90° autour de x
        'tip_backward': [-0.707, 0, 0, 0.707],# -90° autour de x
        'tip_right':    [0, 0.707, 0, 0.707], # 90° autour de y
        'tip_left':     [0, -0.707, 0, 0.707],# -90° autour de y
        'upside_down':  [1, 0, 0, 0]# 180° autour de x
        } #TODO: pb pour upside_down??
    
    if turn not in rotations:
        print(f"chagement d'orientation non traité: {turn}")
        return item
    
    #aja que les quaternions marchent avec des multiplications matricielle. enfin. j'avais déjà appris ça. il a fallu revoir.
    change = rotations[turn]
    x1, y1, z1, w1 = current
    x2, y2, z2, w2 = change
    new_quat = [w1*x2 + x1*w2 + y1*z2 - z1*y2, w1*y2 - x1*z2 + y1*w2 + z1*x2, w1*z2 + x1*y2 - y1*x2 + z1*w2, w1*w2 - x1*x2 - y1*y2 - z1*z2]
    item['quat'] = new_quat
    return item


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

    reste = [rel for rel in relations if rel.get('object', '') in items_dict and rel.get('subject', '') in items_dict]

    while reste:
        progression = False
        for rel in reste[:]:
            item_id = rel['object']
            subject_id = rel['subject']
            item = items_dict[item_id]
            subject = items_dict[subject_id]
            if item_id not in placed_items:
                continue
            else:
                changePosFromRel(rel, item, subject)
                placed_items.add(subject_id)
                reste.remove(rel)
                progression = True
        if not progression:
            print(f"[sceneBuilding] Relations impossibles à résoudre, ignorées : {reste}")
            break
    return items

def processOrientations(items,orientations):
    '''
    Adapte les quaternions des items en fonctions des changements d'orientation.

    :param items: liste de dict d'items
    :param relations: les changements d'orientation
    :return: items, les items avec les bonnes orientations
    '''
    items_dict = {item['id']: item for item in items} #pour pouvoir acceder aux differents items plus facilement   
    for ori in orientations:
        id = ori['id']
        turn = ori['turn']
        item = items_dict[id]
        changeQuatFromTurn(turn, item)

    return items

def buildScene(items, relations, orientations): #TODO verif si autres trucs needed
    '''
    Ajoute à une liste de dictionnaires (un dict par item), toutes les infos nécessaies à la simulation, donc path et pos
    '''
    for item in items:
        item['path'] = getFilePath(item)
    items = processRelations(items,relations)
    items = processOrientations(items,orientations)
    return items