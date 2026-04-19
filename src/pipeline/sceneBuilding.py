import os
import random
from .itemSpec import getOriginalDimensions, getFilePath
from .jsonParsing import simplifyRelations


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
        s = item.get('scale', 1.0)
        item['pos'] = (0, 0, 0.01 + height * s / 2)
        if not item.get('quat'):
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
        if item.get('root') in (True, 'true', 'True'):
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
    processed = True
    if not item.get('dimensions'):
        item = getOriginalDimensions(item)
    s_item = item.get('scale', 1.0)
    width, depth, height = [d * s_item for d in item['dimensions']]
    (x,y,z) = item['pos']
    if not subject.get('dimensions'):
        subject = getOriginalDimensions(subject)
    s_sub = subject.get('scale', 1.0)
    subject_w, subject_d, subject_h = [d * s_sub for d in subject['dimensions']]
    (subject_x, subject_y, subject_z) = subject['pos']

    isDistance = False
    distance = 0
    if rel.get('distance'):
        distance = rel['distance']
        isDistance = True

    if rel['type'] == 'on':
        subject_x += random.uniform(x - width/2 + subject_w/2, x + width/2 - subject_w/2) #prise en compte des dims du sujet pour ne pas etre trop au bord
        subject_y += random.uniform(y - depth/2 + subject_d/2, y + depth/2 - subject_d/2)
        subject_z += z + height/2
    elif rel['type'] == 'in_front_of':
        if isDistance:
            subject_x += x + width/2 + subject_w/2 + distance
            subject_z = z
        else:
            subject_x += random.uniform(x + width/2 + subject_w/2, x + width + subject_w/2)
            subject_z = z
    elif rel['type'] == 'behind':
        if isDistance:
            subject_x += x - width/2 - subject_w - distance
            subject_z = z
        else:
            subject_x += random.uniform(x - width/2 - subject_w , x - width - subject_w/2) #temp fix
            subject_z = z
    elif rel['type'] == 'right_of': 
        if isDistance:
            subject_y += y + depth/2 + subject_d/2 + distance
            subject_z = z
        else:
            subject_y += random.uniform(y + depth/2 + subject_d/2, y + depth + subject_d/2)
            subject_z = z
    elif rel['type'] == 'left_of':
        if isDistance:
            subject_y += y - depth/2 - subject_d/2 - distance
            subject_z = z
        else:
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
        if isDistance:
            subject_x = x + width/2 + subject_w/2 + distance
        else:
            subject_x = x + width/2 + subject_w/2 + random.uniform(0.1, 0.4)
        subject_y = y
        subject_z = z
        qx, qy, qz, qw = subject.get('quat', [0, 0, 0, 1])
        new_quat = [-qy, qx, qw, -qz] 
        subject['quat'] = new_quat
    else:
        print("relation non traitée: ", rel['type'])
    subject['pos'] = (subject_x, subject_y, subject_z)
    


def changeQuatAndPosFromTurn(turn, item):
    '''
    Change les données d'orientation du sujet
    '''
    current = item.get('quat', [0, 0, 0, 1])
    if not item.get('dimensions'):
        item = getOriginalDimensions(item)
    (width, depth, height) = item['dimensions']
    rotations = {
        'tip_left':[0, 0, 0.707, 0.707],
        'tip_right':[0, 0, -0.707, 0.707],
        'upside_down': [0, 0, 1, 0],
        'tip_forward':[0.707, 0, 0, 0.707],
        'tip_backward':[-0.707, 0, 0, 0.707],
        'turn_right':[0, 0.707, 0, 0.707], 
        'turn_left': [0, -0.707, 0, 0.707],
        'turn_around':[1, 0, 0, 0]}
    
    if turn not in rotations:
        print(f"chagement d'orientation non traité: {turn}")
        return item
    
    #aja que les quaternions marchent avec des multiplications matricielle. enfin. j'avais déjà appris ça. il a fallu revoir.
    change = rotations[turn]
    x1, y1, z1, w1 = current
    x2, y2, z2, w2 = change
    new_quat = [w1*x2 + x1*w2 + y1*z2 - z1*y2, w1*y2 - x1*z2 + y1*w2 + z1*x2, w1*z2 + x1*y2 - y1*x2 + z1*w2, w1*w2 - x1*x2 - y1*y2 - z1*z2]
    item['quat'] = new_quat

    #et ensuite on change les dimensions vu que le dessus de l'objet n'et plus le meme etc...
    if turn == 'turn_left' or turn == 'turn_right':
        item['dimensions'] = (depth, width, height)
    elif turn == 'tip_forward' or turn == 'tip_backward':
        item['dimensions'] = (width, height, depth)
    elif turn == 'tip_right' or turn == 'tip_left':
        item['dimensions'] = (height, depth, width)

    return item


def processRelations(items, relations):
    '''
    Adapte les coordonnees x,y,z des items en fonction des relations.

    :param items: liste de dict d'items
    :param relations: les relations entre les items
    :return: items, les items avec les bonnes coordonnées et les bonnes 
    '''

    items_dict = {item['id']: item for item in items} #pour pouvoir acceder aux differents items plus facilement

    placed_items = getRoot(items)
    
    relations = simplifyRelations(relations)

    reste = [rel for rel in relations if rel.get('object', '') in items_dict and rel.get('subject', '') in items_dict]

    while reste:
        progression = False
        for rel in reste[:]:
            item_id = rel['object']
            subject_id = rel['subject']
            if item_id not in items_dict:
                print(f"ATTENTION: ID objet inconnu dans relation: '{item_id}'")
            if subject_id not in items_dict:
                print(f"ATTENTION: ID objet inconnu dans relation: '{subject_id}'")
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
        print(f"Avant: {id} quat={item.get('quat')}")
        changeQuatAndPosFromTurn(turn, item)
        print(f"Après: {id} quat={item.get('quat')}")
    return items


def buildScene(items, relations, orientations): #TODO c'est très moche comme façon de faire
    '''
    Ajoute à une liste de dictionnaires (un dict par item), toutes les infos nécessaies à la simulation, donc path et pos
    '''
    for item in items:
        item['path'] = getFilePath(item)
        if not item.get('dimensions'):
            item = getOriginalDimensions(item)
    items = processOrientations(items,orientations)
    items = initPosAndQuat(items)
    items = processRelations(items,relations)
    return items