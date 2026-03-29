import os

from PyQt6.QtCore import QObject, pyqtSignal

from promptToJson import instruction_to_json, get_available_objects
from jsonParsing import readJSON
from sceneBuilding import buildScene

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
SCENE_OUTPUT_FILE = os.path.join(SRC_DIR, '..', 'scene_generee.json')


class PipelineWorker(QObject):
    status_update = pyqtSignal(str) # mettre a jour le petit label de status 
    scene_ready = pyqtSignal(list) # mettre a jour la vue 2D, possible de sup 
    unrecognized_objects = pyqtSignal(list, list) # les objets pas reconnus par le LLM 
    error_occurred = pyqtSignal(str) # n'importe quelle erreur
    finished = pyqtSignal() # reactive le bouton envoyer 

    def __init__(self, instruction):
        super().__init__()
        self.instruction = instruction

    def run(self):
        try:
            self.status_update.emit("Envoi du prompt au LLM >:D ") # premier status update
            scene_json, non_reconnus = instruction_to_json(self.instruction, SCENE_OUTPUT_FILE)
            if non_reconnus:
                self.unrecognized_objects.emit(non_reconnus, get_available_objects())

            self.status_update.emit("JSON genere. Calcul des coordonnees 3D <33")
            objets, relations = readJSON(SCENE_OUTPUT_FILE)
            objetsList = buildScene(objets, relations)
            self.scene_ready.emit(objetsList) # creer la scene 2D just for show 
        except (ConnectionError, RuntimeError, ValueError) as e:
            self.error_occurred.emit(str(e)) # erreur qu'on connait
        except Exception as e:
            self.error_occurred.emit(f"Erreur non recoonnue : {str(e)}") # erreur de genesis 
        finally:
            self.finished.emit()
            
# lance genesis via launch_genesis pour la simulation reel dans genesis
