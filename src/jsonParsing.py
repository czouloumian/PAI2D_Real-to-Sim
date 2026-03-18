import json

def readJSON(path):
    '''
    Lit le JSON et extrait les informations en liste d'items et leur relations

    :param path: le path du fichier JSON
    :return items: la liste de dicts d'item contenant id et urdf
    :return relations: la liste de dicts de relations (type, subject, item)
    '''
    with open(path, 'r') as file:
        data = json.load(file)
    items = data.get('Objets', [])
    relations = data.get('Relations', [])
    relations = simplifyRelations(relations)

    return items, relations


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