import json
import os
from jsonToSim import create_scene, create_scene_validation, validation_physique
from validationVLM import getFilePath, getOriginalDimensions
from boucle_validation.validation_prompt import boucle_vlm

def main():
    path = os.path.join(os.path.dirname(__file__), 'exemple.json')
    with open(path, 'r') as file:
        data = json.load(file)
    #itemsList = data.get('objets', [])
    #itemsList = getFilePath(itemsList) #TODO: a changer plus tard
    #itemsList = getOriginalDimensions(itemsList) #TODO: a changer plus tard

    prompt = "Sur une table, je veux des ciseaux à droite d'un mug et une banane à sa gauche."
    scene_finale = boucle_vlm(prompt, path)
    create_scene(scene_finale)

    #corrected = validation_physique(itemsList)
    #create_scene(corrected) 
    
    #boucle de validation avec le VLM:
    #path_to_screenshot = create_scene_validation(itemsList)
    #prompt = "Je veux des ciseaux à droite d'un mug et une banane à sa gauche."
    #validation = boucle_vlm(prompt, path)
    #print("Validation:", validation)

    #truc de prompt de base
    #simul genesis
    #boucle VLM de validation et correction

if __name__=="__main__":
    main()