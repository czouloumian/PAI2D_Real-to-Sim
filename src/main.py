import os

from simulationGenesis import create_scene
from jsonToCoord import createObjectList, readJSON
from promptToJson import instruction_to_json

def main():
    print("Décrivez la scène de simulation désirée:")
    instruction = input()
    instruction_to_json(instruction, output_file="scene.json")
    path = os.path.join(os.path.dirname(__file__), 'scene.json')
    objets, relations = readJSON(path)
    objetsList = createObjectList(objets, relations)
    create_scene(objetsList)

if __name__=="__main__":
    main()