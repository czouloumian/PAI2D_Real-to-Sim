import os

from simulationGenesis import create_scene
from jsonToCoord import createObjectList, readJSON

def main():
    path = os.path.join(os.path.dirname(__file__), 'infos.json')
    objets, relations = readJSON(path)
    objetsList = createObjectList(objets, relations)
    create_scene(objetsList)

if __name__=="__main__":
    main()