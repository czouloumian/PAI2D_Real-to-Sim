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
        if item.get('root') is True:
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

    # filtrer les relations dont les IDs n'existent pas dans les items (sécurité)
    reste = [rel for rel in relations
             if rel.get('object', '') in items_dict and rel.get('subject', '') in items_dict]

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


def buildScene(items, relations): #TODO verif si autres trucs needed
    '''
    Ajoute à une liste de dictionnaires (un dict par item), toutes les infos nécessaies à la simulation, donc path et pos
    '''
    for item in items:
        item['path'] = getFilePath(item)
    items = processRelations(items,relations)
    return items