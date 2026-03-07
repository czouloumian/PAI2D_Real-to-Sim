import genesis as gs


def create_scene(objetsList):
    '''
    Fonction qui permet de creer la scene sur genesis à partir des infos objenues précédemment.
    On commence par initialiser une scène vide, puis on rajoute les objets URDF.

    :param objets: une liste de dictionnaires des infos pour chaque objet (id, urdf, path, pos)
    '''
    gs.init(backend=gs.cuda)

    scene = gs.Scene(show_viewer=True)

    plane = scene.add_entity(gs.morphs.Plane()) #la ground plaine

    #ajout des objets: une boucle for qui prend l'objet, sa position, son filepath, et qui crée les objets un par un
    for obj in objetsList:
        entity = scene.add_entity(
            gs.morphs.URDF(
                file=obj['path'],
                pos=obj['pos'],
                scale=1.0,
            ),
           # material=gs.materials.Rigid(rho=1000) #pour essayer de regler le pb d'objets pas solides
        )

    scene.build()

    for i in range(1000):
        scene.step()
