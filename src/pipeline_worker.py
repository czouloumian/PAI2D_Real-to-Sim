import os
import json
import traceback

from PyQt6.QtCore import QObject, pyqtSignal
from promptToJson_auxilieres import object_rec, objets_list, suggest_alternatives,classify_intent, OBJETS_DIR
from promptToJson_V2_LLM import object_dim_quat, modify_scene
from promptToJson_V1_prim import object_relations
from sceneBuilding import buildScene

# V1 : placement via relations + sceneBuilding | V2 : LLM calcule direct les coords
PIPELINE_VERSION = "V1"

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
SCENE_OUTPUT_FILE = os.path.join(SRC_DIR, '..', 'scene_generee.json')


def _place_objects(prompt, objet_reconnus):
    """Place les objets selon la version du pipeline choisie."""
    if PIPELINE_VERSION == "V1":

        relations_data = object_relations(prompt, objet_reconnus)
        root_id = relations_data.get("root", "")
        relations = relations_data.get("relations", [])

        items = []
        for label, info in objet_reconnus.items():
            items.append({
                "id": label,
                "urdf": info["urdf"],
                "dimensions": info.get("dimensions"),
                "root": (label == root_id),
            })

        # Si le root retourné ne correspond à aucun item, marquer le premier
        if root_id not in objet_reconnus and items:
            print(f"[V1] root '{root_id}' introuvable, fallback sur '{items[0]['id']}'")
            items[0]["root"] = True

        items = buildScene(items, relations)

        for item in items:
            pos = item.get("pos", (0, 0, 0))
            item["pos"] = list(pos)
            quat = item.get("quat", (0, 0, 0, 1))
            x, y, z, w = quat
            item["quat"] = [w, x, y, z]
            if "scale" not in item:
                item["scale"] = 1.0

        return items
    else:
        return object_dim_quat(prompt, objet_reconnus)


def _modify_scene(prompt, current_objects_json, objet_reconnus):
    """Modifie la scene existante (utilise toujours le LLM direct / V2)."""
    return modify_scene(prompt, current_objects_json, objet_reconnus)


def resolve_urdf_path(path):
    """Resout le chemin vers le fichier URDF exploitable."""
    if os.path.isfile(path):
        return path
    if os.path.isdir(path):
        for name in ["mobility.urdf", "kinbody.xml"]:
            urdf = os.path.join(path, name)
            if os.path.exists(urdf):
                return urdf
    return path


def postprocess_objects(objetsList, objet_reconnus):
    """Post-traitement commun : resoudre les paths URDF, convertir les quaternions, sauvegarder"""
    print(f"[POSTPROCESS] Post-traitement de {len(objetsList)} objets...")
    for obj in objetsList:
        # ajouter le path depuis objet_reconnus si absent
        if "path" not in obj and obj.get("id") in objet_reconnus:
            obj["path"] = objet_reconnus[obj["id"]]["path"]
        # resoudre le path vers le fichier .urdf
        if "path" in obj:
            obj["path"] = resolve_urdf_path(obj["path"])
        # le LLM retourne [w,x,y,z], scipy attend [x,y,z,w]
        if "quat" in obj and len(obj["quat"]) == 4:
            w, x, y, z = obj["quat"]
            obj["quat"] = [x, y, z, w]

    with open(SCENE_OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(objetsList, f, indent=2, ensure_ascii=False)
    print(f"[POSTPROCESS] JSON sauvegarde → {SCENE_OUTPUT_FILE}")

    return objetsList


class RecognitionWorker(QObject):
    """Phase 1 : reconnaissance des objets + suggestion d'alternatives pour les non reconnus."""
    status_update = pyqtSignal(str)
    recognition_done = pyqtSignal(dict, list, dict)  # objet_reconnus, non_reconnus, alternatives_map
    scene_ready = pyqtSignal(list)  # si tout est reconnu, on enchaine directement
    error_occurred = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, prompt):
        super().__init__()
        self.prompt = prompt
        

    def run(self):
        try:
            print(f"[RecognitionWorker] Demarrage reconnaissance | prompt: '{self.prompt}'")
            self.status_update.emit("Reconnaissance des objets...")
            objet_reconnus, non_reconnus = object_rec(self.prompt)

            if non_reconnus:
                # proposer des alternatives pour chaque objet non reconnu
                print(f"[RecognitionWorker] Objets non reconnus : {non_reconnus} — recherche d'alternatives...")
                self.status_update.emit("Recherche d'alternatives...")
                alternatives_map = {}
                for label in non_reconnus:
                    alts = suggest_alternatives(label)
                    print(f"[RecognitionWorker] Alternatives pour '{label}': {alts}")
                    alternatives_map[label] = alts
                self.recognition_done.emit(objet_reconnus, non_reconnus, alternatives_map)

                if not objet_reconnus:
                    # rien de reconnu du tout, on laisse l'UI gerer
                    return
                return

            if not objet_reconnus:
                self.error_occurred.emit("Aucun objet reconnu dans la description.")
                return

            # tout est reconnu, on enchaine avec le placement
            print(f"[RecognitionWorker] Tous reconnus : {list(objet_reconnus.keys())} → placement direct")
            self.status_update.emit("Calcul des positions et orientations...")
            objetsList = _place_objects(self.prompt, objet_reconnus)
            objetsList = postprocess_objects(objetsList, objet_reconnus)
            self.scene_ready.emit(objetsList)

        except (ConnectionError, RuntimeError, ValueError) as e:
            self.error_occurred.emit(str(e))
        except Exception as e:
            traceback.print_exc()
            self.error_occurred.emit(f"Erreur inattendue : {str(e)}")
        finally:
            self.finished.emit()


class PlacementWorker(QObject):
    """Phase 2 : calcul des positions/orientations apres resolution des objets"""
    status_update = pyqtSignal(str)
    scene_ready = pyqtSignal(list)
    error_occurred = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, prompt, objet_reconnus):
        super().__init__()
        self.prompt = prompt
        self.objet_reconnus = objet_reconnus

    def run(self):
        try:
            print(f"[PlacementWorker] Calcul positions pour : {list(self.objet_reconnus.keys())}")
            self.status_update.emit("Calcul des positions et orientations...")
            objetsList = _place_objects(self.prompt, self.objet_reconnus)
            objetsList = postprocess_objects(objetsList, self.objet_reconnus)
            self.scene_ready.emit(objetsList)

        except (ConnectionError, RuntimeError, ValueError) as e:
            self.error_occurred.emit(str(e))
        except Exception as e:
            traceback.print_exc()
            self.error_occurred.emit(f"Erreur inattendue : {str(e)}")
        finally:
            self.finished.emit()


class ModifySceneWorker(QObject):
    """Modifie une scene existante selon le prompt utilisateur."""
    status_update = pyqtSignal(str)
    scene_ready = pyqtSignal(list)
    error_occurred = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, prompt, current_objects_json, objet_reconnus):
        super().__init__()
        self.prompt = prompt
        self.current_objects_json = current_objects_json
        self.objet_reconnus = objet_reconnus

    def run(self):
        try:
            print(f"[ModifySceneWorker] Modification de la scene | prompt: '{self.prompt}'")
            print(f"[ModifySceneWorker] Scene actuelle : {self.current_objects_json[:200]}...")
            self.status_update.emit("Modification de la scene...")
            objetsList = _modify_scene(self.prompt, self.current_objects_json, self.objet_reconnus)
            objetsList = postprocess_objects(objetsList, self.objet_reconnus)
            self.scene_ready.emit(objetsList)

        except (ConnectionError, RuntimeError, ValueError) as e:
            self.error_occurred.emit(str(e))
        except Exception as e:
            traceback.print_exc()
            self.error_occurred.emit(f"Erreur inattendue : {str(e)}")
        finally:
            self.finished.emit()


class IntentWorker(QObject):
    """Classifie le prompt en 'new_scene' ou 'modify_scene'."""
    intent_classified = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, prompt, scene_summary):
        super().__init__()
        self.prompt = prompt
        self.scene_summary = scene_summary

    def run(self):
        try:
            print(f"[IntentWorker] Classification de l'intent | prompt: '{self.prompt}'")
            intent = classify_intent(self.prompt, self.scene_summary)
            print(f"[IntentWorker] Intent retourne : '{intent}'")
            self.intent_classified.emit(intent)
        except (ConnectionError, RuntimeError, ValueError) as e:
            self.error_occurred.emit(str(e))
        except Exception as e:
            traceback.print_exc()
            self.error_occurred.emit(f"Erreur inattendue : {str(e)}")
        finally:
            self.finished.emit()
