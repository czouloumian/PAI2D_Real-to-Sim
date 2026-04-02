import os
import json
import traceback

from PyQt6.QtCore import QObject, pyqtSignal

from promptToJson_ import object_rec, object_dim_quat, objets_list, OBJETS_DIR

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
SCENE_OUTPUT_FILE = os.path.join(SRC_DIR, '..', 'scene_generee.json')


def resolve_urdf_path(path):
    """Resout le chemin vers le fichier URDF exploitable.
    objets_list retourne le dossier (ex: objets/10357_poubelle),
    mais le viewer 3D a besoin du .urdf (ex: objets/10357_poubelle/mobility.urdf)"""
    if os.path.isfile(path):
        return path
    if os.path.isdir(path):
        for name in ["mobility.urdf", "kinbody.xml"]:
            urdf = os.path.join(path, name)
            if os.path.exists(urdf):
                return urdf
    return path


class PipelineWorker(QObject):
    status_update = pyqtSignal(str)
    scene_ready = pyqtSignal(list)
    unrecognized_objects = pyqtSignal(list, list)
    error_occurred = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, instruction):
        super().__init__()
        self.instruction = instruction

    def run(self):
        try:
            # Phase 1 : reconnaissance des objets
            self.status_update.emit("Reconnaissance des objets...")
            print("user-prompt:",self.instruction)
            objet_reconnus, non_reconnus = object_rec(self.instruction)

            if non_reconnus:
                available = list(objets_list(OBJETS_DIR).keys())
                self.unrecognized_objects.emit(non_reconnus, available)

            if not objet_reconnus:
                self.error_occurred.emit("Aucun objet reconnu dans la description.")
                return

            # Phase 2 : placement spatial (scale, quat, pos)
            self.status_update.emit("Calcul des positions et orientations...")
            objetsList = object_dim_quat(self.instruction, objet_reconnus)

            # Post-traitement
            for obj in objetsList:
                # Resoudre le path vers le fichier .urdf
                if "path" in obj:
                    obj["path"] = resolve_urdf_path(obj["path"])

                # Convertir quat de [w, x, y, z] (format LLM) vers [x, y, z, w] (format scipy)
                if "quat" in obj and len(obj["quat"]) == 4:
                    w, x, y, z = obj["quat"]
                    obj["quat"] = [x, y, z, w]

            # Sauvegarder le JSON pour le bouton telecharger et Genesis
            with open(SCENE_OUTPUT_FILE, 'w', encoding='utf-8') as f:
                json.dump(objetsList, f, indent=2, ensure_ascii=False)

            self.scene_ready.emit(objetsList)

        except (ConnectionError, RuntimeError, ValueError) as e:
            print(f"[ERREUR] {e}")
            self.error_occurred.emit(str(e))
        except Exception as e:
            traceback.print_exc()
            self.error_occurred.emit(f"Erreur inattendue : {str(e)}")
        finally:
            self.finished.emit()
