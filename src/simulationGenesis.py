import genesis as gs

def create_scene(objetsList): #TODO: la gravité est passée où??
    '''
    Fonction qui permet de creer la scene sur genesis à partir des infos objenues précédemment.
    On commence par initialiser une scène vide, puis on rajoute les objets URDF.

    :param objets: une liste de dictionnaires des infos pour chaque objet (id, urdf, path, pos)
    '''
    gs.init(backend=gs.cpu)

    scene = gs.Scene(show_viewer=True)

    plane = scene.add_entity(gs.morphs.Plane())

    #ajout des objets: une boucle for qui prend l'objet, sa position, son filepath, et qui crée les objets un par un
    for obj in objetsList:
        entity = scene.add_entity(
            gs.morphs.URDF(
                file=obj['path'],
                pos=obj['pos'], 
                quat=obj.get('quat', [0.0, 1.0, 1.0, 0.0]),
                scale=obj.get('scale', 1.0),
            ),
            material=gs.materials.Rigid(rho=1000),
        )

    scene.build()

    for i in range(1000):
        scene.step()