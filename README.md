# PAI2D Real-to-Sim

Binôme: Anais Azouaoui et Caroline Zouloumian

Notre projet PAI2D, ayant pour but l'automatisation de scènes 3D de simulation robotique depuis des prompts textuels et d'images.
Notre [cahier des charges](documentation/cahier_des_charges.pdf) présente le projet plus en détails.

#### (Projet et documentation en cours)


---

## Installations

**1. Cloner le projet:**

```  bash
git clone https://github.com/czouloumian/PAI2D_Real-to-Sim.git
cd PAI2D_Real-to-Sim
``` 

**2. Créer un environnement conda**

```  bash
conda create -n realtosim-env -y
conda activate realtosim-env
``` 

**3. Installer PyTorch, Genesis et Ollama (et les modèles llama 3.1 et 3.2-Vision)**

```  bash
pip install torch torchvision
pip install genesis-world
curl -fsSL https://ollama.com/install.sh | sh
ollama run llama3.1
ollama run llama3.2-vision
``` 

## Exécution du projet:

**Note: Cette instruction permet d'exécuter la version actuelle du projet, donc la génération automatique d'une scène rudimentaire sur genesis. Il ne s'agit pas de la version finale du projet.**

```  bash
python src/main.py
``` 

## Structure du projet:
(documentation en cours)