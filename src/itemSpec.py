import os
import trimesh
import xml.etree.ElementTree as ET


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


def getOriginalDimensions(item):
    '''
    Extrait les dimensions de l'item URDF, qui sont dans '<geometry>'

    :param filepath: le path pour le file urdf
    :return: l'item avec ses dimensions
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


def processScale(item): #TODO: is it going to be un indice de multiplication? are we adding a scale attribute to the item, that we can then give to the simulation?
    #TODO: check what scale actually does in the genesis simul: it seems like it makes it do weird stuff
    '''
    Gets the dimension of the item and compares them to the dimensions that the item needs to have in the simulation.
    Defines the scale at which the object will be displayed. Give new dimensions to the items so that positions can be processed accordingly.
    '''
    (item_w, item_d, item_h) = item['dimensions']
    if item['mesures']:
        (new_w, new_d, new_h) = item['mesures'] #TODO: 'mesures' à rajouter au prompt ou autre, c'est les mesures de l'objet ajoutées par l'utilisateur 
        item['scale'] # = scale such that item * scale = new
    return item