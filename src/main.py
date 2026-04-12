import os

from simulationGenesis import create_scene
from sceneBuilding import buildScene
from jsonParsing import readJSON

def main():
    #print("Décrivez la scène de simulation désirée:")
    #instruction = input()
    #instruction_to_json(instruction, output_file="scene.json")
    path = os.path.join(os.path.dirname(__file__), 'test.json')
    objets, relations, orientations = readJSON(path)
    objetsList = buildScene(objets, relations, orientations)
    create_scene(objetsList)

if __name__=="__main__":
    main()