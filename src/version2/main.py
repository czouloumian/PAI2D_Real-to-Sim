import json
import os
from jsonToSim import create_scene, create_scene_validation
from validationVLM import boucle_vlm, getFilePath, getOriginalDimensions

def main():
    path = os.path.join(os.path.dirname(__file__), 'exemple.json')
    with open(path, 'r') as file:
        data = json.load(file)
    itemsList = data.get('objets', [])
    #itemsList = getFilePath(itemsList) #TODO: a changer plus tard
    itemsList = getOriginalDimensions(itemsList) #TODO: a changer plus tard
    
    create_scene(itemsList)
    
    #boucle de validation avec le VLM:
    #path_to_screenshot = create_scene_validation(itemsList)
    #prompt = "Je veux des ciseaux, un mug et une banane sur une table." #TODO: ana aura un truc qui donne les objets disponibles
    #validation = boucle_vlm(prompt, path, path_to_screenshot)
    #print("Validation:", validation)

    #truc de prompt de base
    #simul genesis
    #boucle VLM de validation et correction

if __name__=="__main__":
    main()