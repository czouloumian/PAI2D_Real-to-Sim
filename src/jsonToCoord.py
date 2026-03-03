import json
import os
import xml.etree.ElementTree as ET


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
        
    return path


def getDimensions(filepath):
    '''
    Extrait les dimensions de l'objet URDF, qui sont dans '<geometry>'

    :param filepath: le path pour le file urdf
    :return: dimensions de l'objet
    '''
    #TODO: parser l'objet urdf
    width= 0
    depth=0
    height=0

    tree = ET.parse(filepath) #lecture du fichier urdf en xml
    root = tree.getroot()
    
    for geometry in root.iter('geometry'):
        box= geometry.find('box')
        if box is not None:
            size = box.attrib['size'].split()
            return (float(size[0]),float(size[1]), float(size[2]))

    #TODO: regarder s'il y a d'autres choses possible que box
    print("Dimensions non trouvées")
    return (0.1,0.1,0.1)


def isRootObject(): #TODO, pour l'instant True pour tester le flow du reste
    return True


def generateCoord(objet):
    '''
    Genere les coordonnees x,y,z de l'objet en fonction de sa relation avec un autre objet.
    '''
    #on, under, next_to, in
    (width, depth, height) = getDimensions(objet['path'])

    #TODO: fonction isrootobject qui determine en fonction des relations si cet objet est celui a qui on va donner les coords de bases, 
    # en fonction desquelles on va déterminer les autres.

    if isRootObject():
        return (0,0,0)

    else:
        pass


def createObjectList(objets):
    '''
    Ajoute à une liste de dictionnaires (un dict par objet), toutes les infos nécessaies à la simulation, donc path et pos
    '''
    for obj in objets:
        obj['path'] = getFilePath(obj)
        obj['pos'] = generateCoord(obj)
    return objets