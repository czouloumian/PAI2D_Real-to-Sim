import os
import genesis as gs

def create_scene(path):
    '''
    Fonction qui permet de creer la scene sur genesis à partir des infos objenues précédemment.
    On commence par initialiser une scène vide, puis on rajoute les objets URDF.

    :param objets: une liste de dictionnaires des infos pour chaque objet (id, urdf, path, pos)
    '''
    gs.init(backend=gs.cpu)
    scene = gs.Scene(show_viewer=True, sim_options=gs.options.SimOptions(dt=0.001))
    plane = scene.add_entity(gs.morphs.Plane())
    entity = scene.add_entity(
        gs.morphs.URDF(
            file=path
        ),
        material=gs.materials.Rigid(rho=1000),
    )
    scene.build()
    for i in range(1000):
        scene.step()
    gs.destroy()
    

def main():
    #ceux qui marchent: le robinet,
    liste_partnet_marche = ["154_robinet/mobility.urdf", "8867_porte_battante_2/mobility.urdf", "9032_porte_coulissante/mobility.urdf", 
                            "10357_poubelle/mobility.urdf", "100073_cle_usb/mobility.urdf"]

    #ceux qui ne marchent pas: les erreurs sont differentes selon les objets
    liste_partnet_marche_pas = ["7138_four/mobility.urdf", "10143_refrigerateur/mobility.urdf", "10211_ordinateur_portable/mobility.urdf", 
                                "11826_lave_linge/mobility.urdf", "10357_poubelle/mobility.urdf", "11826_lave_linge/mobility.urdf",
                                "44817_meuble_tiroirs/mobility.urdf","100658_boite_carton_ouverte/mobility.urdf","103369_lave_vaisselle/mobility.urdf",
                                "103477_toaster/mobility.urdf"]

    liste_partnet = ["154_robinet/mobility.urdf", "7138_four/mobility.urdf", 
                 "8867_porte_battante_2/mobility.urdf", "9032_porte_coulissante/mobility.urdf",
                 "10143_refrigerateur/mobility.urdf","10211_ordinateur_portable/mobility.urdf", 
                 "10357_poubelle/mobility.urdf","11826_lave_linge/mobility.urdf",
                 "44817_meuble_tiroirs/mobility.urdf","100073_cle_usb/mobility.urdf", 
                 "100658_boite_carton_ouverte/mobility.urdf", "103369_lave_vaisselle/mobility.urdf",
                 "103477_toaster/mobility.urdf"]
    for filename in liste_partnet:
        items_folder = os.path.join(os.path.dirname(__file__),'..', 'objets')
        path = os.path.join(items_folder, filename)
        create_scene(path)

if __name__=="__main__":
    main()