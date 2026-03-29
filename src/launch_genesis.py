import sys
import os

sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from jsonParsing import readJSON
from sceneBuilding import buildScene
from simulationGenesis import create_scene

if __name__ == "__main__":
    scene_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "scene_gen.json")
    objets,relations = readJSON(scene_path)
    objetsList = buildScene(objets, relations)
    create_scene(objetsList)
