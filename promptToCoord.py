import ollama
import subprocess
import time
import json


def ollama_run(): #TODO ne marche pas vraiment (ou alors mon pc est lent), pour l'instant je teste avec ollama déjà démarré
    '''
    Ouvre Ollama si Ollama n'est pas déjà ouvert, afin que la communication puisse fonctionner.
    '''
    try:
        subprocess.check_output(["pgrep", "Ollama"])
    except subprocess.CalledProcessError:
        print("Starting Ollama")
        subprocess.Popen(["open", "-a", "Ollama"])
        print("it's opennn")
        time.sleep(5)

def info_dans_json(content):
    '''
    Enregistre l'information obtenue du modèle dans un fichier JSON.
    '''
    try:
        json_propre = content.replace("```json", "").replace("```", "").strip()
        data = json.loads(json_propre)
        with open('infos.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        return "Infos enregistrées JSON."
    except Exception as e:
        return f"Erreur en parsant JSON: {e}"


def info_depuis_prompt(prompt_utilisateur):
    '''
    Prompte le modèle (3.1 ici pour les prompts textuelles) et retourne les infos sous un format JSON.
    '''
    ollama_run()
    system_prompt = (
        "Tu es un assistant robotique. Réponds en format JSON. "
        "N'ajoutes aucune explication avant ou après le JSON. "
        "Utilise des doubles guillemets pour les clés et les chaînes de caractères. "
        "Format : {\"objet\": \"nom\", \"x\": 0.0, \"y\": 0.0, \"z\": 0.0, \"quaternions\": [0.0, 0.0, 0.0, 0.0]}. "
        "L'origine est (0,0,0) au centre de la table."
        # + les dimensions de la table??
    )
    response = ollama.chat(model='llama3.1', messages=[
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': prompt_utilisateur},
    ])
    content = response['message']['content']
    print(info_dans_json(content))
    return content


print(info_depuis_prompt("Mets un mug au milieu de la table"))
# print(info_depuis_prompt("Je veux faire une simulation pour une saisie de mug et de ciseaux"))
# print(info_depuis_prompt("Mets un mug à droite de la table"))
# print(info_depuis_prompt("Mets un mug au gauche de la table"))
# print(info_depuis_prompt("Mets un mug en haut de la table"))
# print(info_depuis_prompt("Mets un mug au dessus de la table"))
# print(info_depuis_prompt("Mets un mug en dessous de la table"))
