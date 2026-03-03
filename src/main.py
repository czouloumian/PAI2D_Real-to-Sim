import os

from simulationGenesis import create_scene
from jsonToCoord import createObjectList, readJSON

def main():
    path = os.path.join(os.path.dirname(__file__), 'infos.json')
    objets, relations = readJSON(path)
    objetsList = createObjectList(objets)
    #objets = [{"id": "drawer", "urdf": "drawer.urdf", "pos": (0,0,0)}]
    #objetDicts = getFilePath(objets)
    #print(objetsList)
    #for obj in objetsList:
    #    print(getDimensions(obj['path']))
    create_scene(objetsList)

if __name__=="__main__":
    main()