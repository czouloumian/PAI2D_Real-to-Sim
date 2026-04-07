import genesis as gs
import os
from PIL import Image, ImageDraw, ImageFont #https://pillow.readthedocs.io/en/stable/

#TODO
#prendre le truc pour lire le JSON et extraire les infos des objets
#truc des masses est important probablement
#sauvegarder le screenshot de la scene la plus nouvelle a chaque fois pour pouvoir la donner au VLM

def create_scene(objetsList):
    '''
    Fonction qui permet de creer la scene sur genesis à partir des infos objenues précédemment.
    On commence par initialiser une scène vide, puis on rajoute les objets URDF.

    :param objets: une liste de dictionnaires des infos pour chaque objet (id, urdf, path, pos, quat)
    :return: le chemin vers le screenshot de la scène générée
    '''

    gs.init(backend=gs.cuda)

    scene = gs.Scene(show_viewer=True, sim_options=gs.options.SimOptions(dt=0.01) ) 

    plane = scene.add_entity(gs.morphs.Plane()) #la ground plaine

    cameras = {
        "perspective":scene.add_camera(res=(640, 480), pos=(3.5, 0.0, 2.5), lookat=(0, 0, 0.5), fov=30),
        "top":scene.add_camera(res=(640, 480), pos=(0.0, 0.0, 4.0), lookat=(0, 0, 0),   fov=40),
        "side":scene.add_camera(res=(640, 480), pos=(0.0, 3.5, 1.0), lookat=(0, 0, 0.5), fov=30)
    }

    font = ImageFont.load_default()

    #ajout des objets: une boucle for qui prend l'objet, sa position, son filepath, et qui crée les objets un par un
    for obj in objetsList:
        entity = scene.add_entity(
            gs.morphs.URDF(
                file=obj['path'],
                pos=tuple(obj['pos']),
                quat=tuple(obj['quat'])
            ),
        )

    scene.build()

    for i in range(150):
        scene.step()

    image_paths = []
    base_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'images')
    os.makedirs(base_dir, exist_ok=True)

    #for name, cam in cameras.items():
    #    rgb, _, _, _ = cam.render(rgb=True)
    #    img_path = os.path.abspath(os.path.join(base_dir, f'screenshot_{name}.png'))
    #    Image.fromarray(rgb).save(img_path)
    #    image_paths.append(img_path)


    views = ["perspective", "top", "side"]
    images = []
    
    for name in views:
        rgb, _, _, _ = cameras[name].render(rgb=True)
        images.append(Image.fromarray(rgb))

    widths, heights = zip(*(i.size for i in images))
    total_width = sum(widths)
    max_height = max(heights)

    collage = Image.new('RGB', (total_width, max_height))

    x_offset = 0
    for im in images:
        collage.paste(im, (x_offset, 0))
        x_offset += im.size[0]

    path_collage = os.path.abspath("images/collage_validation.png")
    collage.save(path_collage)


    gs.destroy()
    return path_collage

