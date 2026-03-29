import sys
import os
import shutil
import subprocess

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QSplitter,QVBoxLayout, QHBoxLayout, QTextEdit, QLineEdit,QPushButton, QLabel, QFrame, QMessageBox,QFileDialog, QSizePolicy)
from PyQt6.QtCore import Qt, QThread       
from PyQt6.QtGui import QFont, QColor, QPalette  
from pipeline_worker import PipelineWorker, SRC_DIR, SCENE_OUTPUT_FILE
from scene_3d_view import SceneView3D # pour la scene 3D


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PAI2D Real-to-Sim")
        self.setMinimumSize(1050, 650)
        self._current_objetsList = None # ob conserve la objetList generee pour les boutons download et simulation genesis et eventuellement les modifs 
        # ref au thread et worker en cours (pour eviter les doublon)
        self._thread = None
        self._worker = None

        self._setup_ui() # construit interface
        self._dark_theme() # theme sombre qu'on va changer en rose tkt 

    def _setup_ui(self):
        """Construit la structure generale de l'interface."""
        central = QWidget()
        self.setCentralWidget(central)

        # titre en haut, splitter en dessous
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(10, 8, 10, 8)  
        root_layout.setSpacing(8)                       
        title = QLabel("PAI2D Real-to-Sim")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(QFont("Arial", 15, QFont.Weight.Bold))
        title.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed) # a modif
        root_layout.addWidget(title)

        # splitter horizontal : panneau chat a gauche, panneau scene a droite
        # l'utilisateur peut drag la barre entre les deux pour redimensionner
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(6) 
        splitter.addWidget(self._build_chat_panel())   
        splitter.addWidget(self._build_scene_panel())  
        splitter.setSizes([400, 650])  
        root_layout.addWidget(splitter, stretch=1) # a modif

    def _build_chat_panel(self):
        """Construit le panneau gauche : chat + prompt"""
        panel = QFrame()
        panel.setFrameShape(QFrame.Shape.StyledPanel)  
        layout = QVBoxLayout(panel)
        layout.setSpacing(6)

        label = QLabel("Chat")
        label.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        layout.addWidget(label)

        #zine affichage des messages => tout modif 
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setAcceptRichText(True)
        layout.addWidget(self.chat_display, stretch=1)

        # label de statut pret, en cours)
        self.status_label = QLabel("Pret")
        self.status_label.setStyleSheet("color: #4caf50; font-size: 11px;")
        layout.addWidget(self.status_label)

        # Ligne du bas champ de saisie + bouton envoyer
        input_row = QHBoxLayout()
        self.prompt_input = QLineEdit()
        self.prompt_input.setPlaceholderText("Decrivez la scene s'il vous plait ")
        # Aapuyer sur Entree = cliquer sur Envoyer
        self.prompt_input.returnPressed.connect(self._on_send) # envoie
        input_row.addWidget(self.prompt_input, stretch=1)
        self.send_btn = QPushButton("Envoyer")
        self.send_btn.setFixedWidth(90)
        self.send_btn.clicked.connect(self._on_send)
        input_row.addWidget(self.send_btn)
        layout.addLayout(input_row)

        return panel

    def _build_scene_panel(self):
        """
        Construit le panneau droit : viewer 3D + boutons download/genesis
        """
        panel = QFrame()
        panel.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(panel)
        layout.setSpacing(6)
        label = QLabel("Apercue 3D de la scene")
        label.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        layout.addWidget(label)

        # widget OpenGL pyqtgraph pour afficher la scene en 3D >:D
        self.scene_view = SceneView3D()
        layout.addWidget(self.scene_view, stretch=1)

        # Ligne de boutons en bas du panneau scene
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        # vert : telecharger le fichier JSON de la scene
        self.download_btn = QPushButton("Telecharger la scene")
        self.download_btn.setObjectName("download_btn")  # pour le cibler en CSS
        self.download_btn.setEnabled(False)  # grise tant qu'aucune scene n'est generee
        self.download_btn.setFixedHeight(40)
        self.download_btn.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        self.download_btn.clicked.connect(self._on_download_scene)
        btn_row.addWidget(self.download_btn)

        # bleu : lancer la simulation Genesis dans un process separe
        self.genesis_btn = QPushButton("Lancer simulation Genesis")
        self.genesis_btn.setObjectName("genesis_btn")  # pour le cibler en CSS
        self.genesis_btn.setEnabled(False)
        self.genesis_btn.setFixedHeight(40)
        self.genesis_btn.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        self.genesis_btn.clicked.connect(self._on_launch_genesis)
        btn_row.addWidget(self.genesis_btn)

        layout.addLayout(btn_row)
        return panel

    # ------------------------------------------------------------------ #
    #                         AFFICHAGE DU CHAT                           #
    # ------------------------------------------------------------------ #

    def _append_message(self, text, role):
        """Ajoute un message dans le chat avec un style selon le role.

        role peut etre :
          -"user" : bulle bleue alignee a droite (message de l'utilisateur) # a modif c moche 
          -"assistant IA" : bulle grise alignee a gauche (reponse du systeme)
          -"system" : bulle gris fonce (info systeme)
          -"error" : bulle rouge (erreur)
        """
        styles = {
            "user":("right", "#1565C0", "#e3f2fd"),
            "assistant": ("left",  "#2e3748", "#cfd8dc"),
            "system": ("left",  "#263238", "#eceff1"),
            "error": ("left",  "#7f1d1d", "#ffebee"),
        }
        align, bg, fg = styles.get(role, styles["system"])
        # on injecte du HTML pour creer des bulles de chat stylees # c'est fo c un peu moche for now 
        html = (
            f'<div style="text-align:{align}; margin:3px 0;">'
            f'<span style="display:inline-block; background:{bg}; color:{fg}; '
            f'padding:6px 10px; border-radius:8px; max-width:85%; font-size:13px;">'
            f'{text}</span></div>'
        )
        self.chat_display.append(html)
        # scroll automatique vers le bas pour voir le dernier message
        sb = self.chat_display.verticalScrollBar()
        sb.setValue(sb.maximum())

   
    # le pipeline 
    def _on_send(self):
        """Appele quand l'utilisateur clique Envoyer ou appuie Entree

        Lance le pipeline complet dans un thread separe :
          1 promptToJson : envoie le prompt au LLM -> genere le JSON
          2 jsonParsing : lit le JSON et extrait objets + relations
          3 sceneBuilding: calcule les positions 3D de chaque objet

        """
        instruction = self.prompt_input.text().strip()
        if not instruction:
            return
        # empeche de lancer deux pipelines en parallele
        if self._thread and self._thread.isRunning():
            QMessageBox.information(self, "En cours", "Generation en cours, veuillez patienter svp wesh")
            return

        # affiche le message de l'utilisateur dans le chat
        self._append_message(instruction, "user")
        self.prompt_input.clear()
        # desactive les boutons pendant le traitement D:
        self.send_btn.setEnabled(False)
        self.download_btn.setEnabled(False)
        self.genesis_btn.setEnabled(False)
        self.status_label.setText("En cours...")
        self.status_label.setStyleSheet("color: #ffb74d; font-size: 11px;")

        # cree un thread Qt + un worker qui fait le travail lourd
        self._thread = QThread()
        self._worker = PipelineWorker(instruction)
        self._worker.moveToThread(self._thread)  # le worker tourne dans le thread

        # Connexion d'un peu tout : le worker emet des signaux l'UI reagit
        self._thread.started.connect(self._worker.run)  # demarre le travail
        self._worker.status_update.connect(self._on_status_update) # maj du label status
        self._worker.scene_ready.connect(self._on_scene_ready)  # scene prete -> afficher
        self._worker.unrecognized_objects.connect(self._on_unrecognized) # objets pas reconnus
        self._worker.error_occurred.connect(self._on_error)  # erreur -> afficher
        self._worker.finished.connect(self._on_pipeline_finished)  # reactive les boutons
        self._worker.finished.connect(self._thread.quit)  # arrete le thread
        self._worker.finished.connect(self._worker.deleteLater) # libere la memoire du json actuel 
        self._thread.finished.connect(self._thread.deleteLater)

        self._thread.start()

  
    # call back du pipeline 
    def _on_status_update(self, msg):
        """met a jour le label de statut"""
        self.status_label.setText(msg)

    def _on_scene_ready(self, objetsList):
        """Appele quand le pipeline a fini et que la scene est prete
        on stocke la liste, on met a jour le viewer 3D, et on active les boutons
        """
        self._current_objetsList = objetsList
        self.scene_view.update_scene(objetsList)   # affiche les objets dans le viewer 3D
        names = ", ".join(obj.get("id", "?") for obj in objetsList)
        self._append_message(f"Scene generee avec le(s) objet(s) : {names}.","assistant")
        #{len(objetsList)}
        self.download_btn.setEnabled(True)
        self.genesis_btn.setEnabled(True)

    def _on_download_scene(self):
        """ ouvre le 'Enregistrer sous' pour telecharger le JSON de la scene"""
        dest, _ = QFileDialog.getSaveFileName(self, "Enregistrer la scene", "scene.json", "JSON (*.json)")
        if dest:
            try:
                # copie le fichier scene_generee.json vers la destination 
                shutil.copy2(SCENE_OUTPUT_FILE, dest)
                self._append_message(f"Scene enregistree : {dest}", "system")
            except Exception as e:
                self._append_message(f"Erreur : {e}", "error")

    def _on_launch_genesis(self):
        """Lance le script launch_genesis.py dans une autrree fenetre"""
        if self._current_objetsList is None:
            return
        launcher = os.path.join(SRC_DIR, "launch_genesis.py")
        try:
            subprocess.Popen(
                [sys.executable, launcher, SCENE_OUTPUT_FILE],
                cwd=SRC_DIR
            )
            self._append_message("Simulation Genesis lancee dans une fenetre separee", "system" )
        except Exception as e:
            self._append_message(f"Impossible de lancer Genesis : {e}", "error")

    def _on_unrecognized(self, non_reconnus, available):
        """Affiche les objets que le LLM n'a pas pu trouver dans la bibliotheque

        Montre aussi la liste des objets disponibles pour aider l'utilisateur
        a reformuler sa description # a faire 
        """
        readable = sorted(n.split("_", 1)[-1] if "_" in n else n for n in available) # retire les nombres
        msg = (f"Objet(s) non reconnu(s) dans la bibliotheque : " f"<b>{', '.join(non_reconnus)}</b><br><br>" f"Objets disponibles :<br>{', '.join(readable)}")
        self._append_message(msg, "assistant")

    def _on_error(self, error_msg):
        """Affiche un message d'erreur dans le chat"""
        self._append_message(error_msg, "error")

    def _on_pipeline_finished(self):
        """Appele quand le pipeline est termine 
        Reactive le bouton Envoyer et remet le statut a 'Pret'
        """
        self.send_btn.setEnabled(True)
        self.status_label.setText("Pret")
        self.status_label.setStyleSheet("color: #4caf50; font-size: 11px;")


    # theme
    def _dark_theme(self):
        """theme sombre"""
        app = QApplication.instance()

        # palette 
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#1e1e2e"))  # fond fenetre
        palette.setColor(QPalette.ColorRole.WindowText,QColor("#cdd6f4"))  # texte fenetre
        palette.setColor(QPalette.ColorRole.Base, QColor("#181825"))  # fond des champs
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#1e1e2e"))
        palette.setColor(QPalette.ColorRole.Text,QColor("#cdd6f4"))  # texte des champs
        palette.setColor(QPalette.ColorRole.Button, QColor("#313244"))  # fond boutons
        palette.setColor(QPalette.ColorRole.ButtonText,QColor("#cdd6f4"))  # texte boutons
        palette.setColor(QPalette.ColorRole.Highlight,QColor("#89b4fa"))  # selection
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#1e1e2e"))
        app.setPalette(palette)

        # QSS par widget
        app.setStyleSheet("""
            QMainWindow, QWidget { background: #1e1e2e; }
            QFrame { border: 1px solid #313244; border-radius: 6px; }

            /* Boutons par defaut : gris */
            QPushButton {
                background: #313244; color: #cdd6f4;
                border: 1px solid #45475a; border-radius: 5px;
                padding: 5px 12px;
            }
            QPushButton:hover { background: #45475a; }
            QPushButton:disabled { color: #585b70; background: #1e1e2e; }

            /* Bouton telecharger : vert */
            QPushButton#download_btn {
                background: #40a02b; color: white; border: none;
            }
            QPushButton#download_btn:hover { background: #2d7d1e; }
            QPushButton#download_btn:disabled { background: #313244; color: #585b70; }

            /* Bouton genesis : bleu */
            QPushButton#genesis_btn {
                background: #1565C0; color: white; border: none;
            }
            QPushButton#genesis_btn:hover { background: #0d47a1; }
            QPushButton#genesis_btn:disabled { background: #313244; color: #585b70; }

            QLineEdit {
                background: #313244; color: #cdd6f4;
                border: 1px solid #45475a; border-radius: 4px;
                padding: 5px 8px;
            }
            QTextEdit {
                background: #181825; color: #cdd6f4;
                border: 1px solid #313244; border-radius: 4px;
            }
            QLabel { color: #cdd6f4; background: transparent; border: none; }
            QSplitter::handle { background: #313244; }
            QScrollBar:vertical {
                background: #181825; width: 8px; border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #45475a; border-radius: 4px;
            }
        """)

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("PAI2D Real-to-Sim")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())  


if __name__ == "__main__":
    main()
