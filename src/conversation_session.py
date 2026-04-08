import json


class ConversationSession:
    """Stocke l'etat d'une conversation : scene actuelle, historique, objets en attente"""

    def __init__(self):
        self.reset()

    def reset(self):
        self.objets_list = None # scene actuelle (list[dict] ou None)
        self.objet_reconnus = {} # label -> {urdf, path, dimensions}
        self.history = [] # [{"role": "user"|"assistant", "content": "..."}]
        self.pending_unrecognized = [] # labels en attente de resolution utilisateur
        self.pending_reconnus = {} # reconnus en attente de completion
        self.alternatives_map = {} # {label: [urdf1, urdf2, ...]}
        self.original_prompt = "" # prompt initial (pour Phase 2 apres resolution)

    def add_message(self, role, content):
        self.history.append({"role": role, "content": content})

    def all_resolved(self):
        """True si tous les objets non reconnus ont ete resolus"""
        return len(self.pending_unrecognized) == 0

    def resolve_object(self, label, urdf, objects_data):
        """L'utilisateur choisit un URDF alternatif pour un label non reconnu"""
        if label in self.pending_unrecognized:
            self.pending_unrecognized.remove(label)
        self.pending_reconnus[label] = {
            "urdf": urdf,
            "path": objects_data[urdf]["path"],
            "dimensions": objects_data[urdf]["dimensions"]
        }

    def remove_object(self, label):
        """L'utilisateur choisit de supprimer un objet non reconnu"""
        if label in self.pending_unrecognized:
            self.pending_unrecognized.remove(label)
        self.alternatives_map.pop(label, None)

    def scene_description(self):
        """Serialise la scene actuelle en texte lisible pour l'injecter dans un prompt LLM"""
        if not self.objets_list:
            return "Aucune scene n'existe encore."
        lines = ["Scene actuelle :"]
        for obj in self.objets_list:
            oid = obj.get("id", "?")
            urdf = obj.get("urdf", "?")
            pos = obj.get("pos", [0, 0, 0])
            scale = obj.get("scale", 1.0)
            lines.append(f'- "{oid}" (urdf: {urdf}) pos={pos} scale={scale}')
        return "\n".join(lines)

    def scene_json(self):
        """Retourne la scene actuelle sous forme de chaine JSON."""
        if not self.objets_list:
            return "[]"
        return json.dumps(self.objets_list, indent=2, ensure_ascii=False)
