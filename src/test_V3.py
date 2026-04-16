import sys
import os
import json
from promptToJson_V3_im import scene_from_image


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
IMAGE_PATH = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "images", "test1.png"))


def print_scene(scene, label=""):
    if label:
        print(f"\n{'─' * 50}")
        print(f"  {label}")
        print(f"{'─' * 50}")
    if not scene:
        print("  [aucun objet retourné]")
        return
    for obj in scene:
        print(json.dumps(obj, indent=2, ensure_ascii=False))



print("\n=== TEST : image seule ===")
scene1 = scene_from_image([IMAGE_PATH])
print_scene(scene1, "Résultat — test1.png")
