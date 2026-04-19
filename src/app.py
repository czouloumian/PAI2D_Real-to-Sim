import sys
import os
import shutil
import subprocess
import html
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QSplitter,QVBoxLayout, QHBoxLayout, QTextBrowser, QLineEdit,QPushButton, QLabel, QFrame, QMessageBox,QFileDialog, QSizePolicy)
from PyQt6.QtCore import Qt, QThread, QUrl
from PyQt6.QtGui import QFont, QColor, QPalette
from pipeline_worker import (RecognitionWorker, PlacementWorker, ModifySceneWorker, IntentWorker,ImageSceneWorker, SRC_DIR, SCENE_OUTPUT_FILE, objets_list, OBJETS_DIR)
from ui.scene_3d_view import SceneView3D
from conversation_session import ConversationSession


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PAI2D Real-to-Sim")
        self.setMinimumSize(1050, 650)
        self._current_objetsList = None
        self._thread = None
        self._worker = None
        self._session = ConversationSession()
        self._pending_intent = None
        self._pending_instruction = None

        self._setup_ui()
        self._dark_theme()

    def _setup_ui(self):
        """Construit la structure generale de l'interface"""
        central = QWidget()
        self.setCentralWidget(central)

        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(10, 8, 10, 8)
        root_layout.setSpacing(8)
        title = QLabel("PAI2D Real-to-Sim")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(QFont("Arial", 15, QFont.Weight.Bold))
        title.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        root_layout.addWidget(title)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(6)
        splitter.addWidget(self._build_chat_panel())
        splitter.addWidget(self._build_scene_panel())
        splitter.setSizes([400, 650])
        root_layout.addWidget(splitter, stretch=1)

    def _build_chat_panel(self):
        """Construit le panneau gauche : bouton nouveau thread + chat + prompt"""
        panel = QFrame()
        panel.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(panel)
        layout.setSpacing(6)

        # ligne du haut : titre + bouton nouveau thread
        top_row = QHBoxLayout()
        label = QLabel("Chat")
        label.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        top_row.addWidget(label)
        top_row.addStretch()

        self.new_thread_btn = QPushButton("Nouveau thread")
        self.new_thread_btn.setObjectName("new_thread_btn")
        self.new_thread_btn.setFixedHeight(28)
        self.new_thread_btn.clicked.connect(self._on_new_thread)
        top_row.addWidget(self.new_thread_btn)
        layout.addLayout(top_row)

        # zone affichage des messages — QTextBrowser pour les liens cliquables
        self.chat_display = QTextBrowser()
        self.chat_display.setReadOnly(True)
        self.chat_display.setOpenLinks(False)
        self.chat_display.anchorClicked.connect(self._on_link_clicked)
        layout.addWidget(self.chat_display, stretch=1)

        # label de statut
        self.status_label = QLabel("Pret")
        self.status_label.setStyleSheet("color: #4caf50; font-size: 11px;")
        layout.addWidget(self.status_label)

        # ligne du bas : champ de saisie + bouton image + bouton envoyer
        input_row = QHBoxLayout()
        self.prompt_input = QLineEdit()
        self.prompt_input.setPlaceholderText("Decrivez la scene s'il vous plait ")
        self.prompt_input.returnPressed.connect(self._on_send)
        input_row.addWidget(self.prompt_input, stretch=1)
        self.image_btn = QPushButton("Image")
        self.image_btn.setObjectName("image_btn")
        self.image_btn.setFixedWidth(70)
        self.image_btn.setToolTip("Générer la scène depuis une image (V3)")
        self.image_btn.clicked.connect(self._on_load_image)
        input_row.addWidget(self.image_btn)
        self.send_btn = QPushButton("Envoyer")
        self.send_btn.setFixedWidth(90)
        self.send_btn.clicked.connect(self._on_send)
        input_row.addWidget(self.send_btn)
        layout.addLayout(input_row)

        return panel

    def _build_scene_panel(self):
        """Construit le panneau droit : viewer 3D + boutons download/genesis"""
        panel = QFrame()
        panel.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(panel)
        layout.setSpacing(6)
        label = QLabel("Aperçu 3D de la scene")
        label.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        layout.addWidget(label)

        self.scene_view = SceneView3D()
        layout.addWidget(self.scene_view, stretch=1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.download_btn = QPushButton("Telecharger la scene")
        self.download_btn.setObjectName("download_btn")
        self.download_btn.setEnabled(False)
        self.download_btn.setFixedHeight(40)
        self.download_btn.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        self.download_btn.clicked.connect(self._on_download_scene)
        btn_row.addWidget(self.download_btn)

        self.genesis_btn = QPushButton("Lancer simulation Genesis")
        self.genesis_btn.setObjectName("genesis_btn")
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
        """Ajoute un message dans le chat avec un style selon le role"""
        styles = {
            "user":("right", "#1565C0", "#e3f2fd"),
            "assistant": ("left",  "#2e3748", "#cfd8dc"),
            "system": ("left",  "#263238", "#eceff1"),
            "error": ("left",  "#7f1d1d", "#ffebee"),
        }
        align, bg, fg = styles.get(role, styles["system"])
        html_msg = (
            f'<div style="text-align:{align}; margin:3px 0;">'
            f'<span style="display:inline-block; background:{bg}; color:{fg}; '
            f'padding:6px 10px; border-radius:8px; max-width:85%; font-size:13px;">'
            f'{text}</span></div>'
        )
        self.chat_display.append(html_msg)
        sb = self.chat_display.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ------------------------------------------------------------------ #
    #                     GESTION DES WORKERS (QThread)                   #
    # ------------------------------------------------------------------ #

    def _launch_worker(self, worker):
        """Lance un worker dans un QThread. Retourne False si un thread tourne deja"""
        if self._thread and self._thread.isRunning():
            QMessageBox.information(self, "En cours", "Generation en cours, veuillez patienter.")
            return False

        self.send_btn.setEnabled(False)
        self.status_label.setText("En cours...")
        self.status_label.setStyleSheet("color: #ffb74d; font-size: 11px;")

        self._thread = QThread()
        self._worker = worker
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._cleanup_thread)
        self._thread.finished.connect(self._thread.deleteLater)

        # connecter status_update si le worker l'a
        if hasattr(self._worker, 'status_update'):
            self._worker.status_update.connect(self._on_status_update)

        return True  # les signaux specifiques seront connectes par l'appelant AVANT start

    def _start_thread(self):
        """Demarre le thread (appeler apres avoir connecte les signaux specifiques)"""
        self._thread.start()

    # ------------------------------------------------------------------ #
    #                         ENVOI DU PROMPT                             #
    # ------------------------------------------------------------------ #

    def _on_send(self):
        """Appele quand l'utilisateur clique Envoyer ou appuie Entree."""
        instruction = self.prompt_input.text().strip()
        if not instruction:
            return

        # bloquer si resolution en cours
        if self._session.pending_unrecognized:
            self._append_message("Veuillez d'abord resoudre les objets non reconnus ci-dessus.", "system")
            return

        if self._thread and self._thread.isRunning():
            QMessageBox.information(self, "En cours", "Generation en cours, veuillez patienter.")
            return

        self._append_message(html.escape(instruction), "user")
        self._session.add_message("user", instruction)
        self.prompt_input.clear()
        self.download_btn.setEnabled(False)
        self.genesis_btn.setEnabled(False)

        # si pas de scene existante → nouvelle scene directement
        if self._session.objets_list is None:
            print(f"[PIPELINE] Pas de scene existante -> nouvelle scene | prompt: '{instruction}'")
            self._launch_recognition(instruction)
        else:
            # classifier l'intention
            print(f"[PIPELINE] Scene existante -> classification de l'intent | prompt: '{instruction}'")
            self._pending_instruction = instruction
            worker = IntentWorker(instruction, self._session.scene_description())
            if not self._launch_worker(worker):
                return
            worker.intent_classified.connect(self._on_intent_classified)
            self._start_thread()

    def _on_intent_classified(self, intent):
        """Stocke l'intent — le worker suivant sera lance par _cleanup_thread apres arret du thread."""
        print(f"[INTENT] Classifie : '{intent}'")
        self._pending_intent = intent

    # ------------------------------------------------------------------ #
    #              LANCEMENT DES DIFFERENTS WORKERS                       #
    # ------------------------------------------------------------------ #

    def _launch_recognition(self, prompt):
        """Lance le RecognitionWorker pour une nouvelle scene"""
        print(f"[WORKER] Lancement RecognitionWorker | prompt: '{prompt}'")
        self._session.original_prompt = prompt
        worker = RecognitionWorker(prompt)
        if not self._launch_worker(worker):
            return
        worker.recognition_done.connect(self._on_recognition_done)
        worker.scene_ready.connect(self._on_scene_ready)
        self._start_thread()

    def _launch_placement(self):
        """Lance le PlacementWorker apres resolution des objets non reconnus"""
        # fusionner les reconnus initiaux avec ceux resolus par l'utilisateur
        all_reconnus = {**self._session.pending_reconnus}
        print(f"[WORKER] Lancement PlacementWorker | objets: {list(all_reconnus.keys())}")
        worker = PlacementWorker(self._session.original_prompt, all_reconnus)
        if not self._launch_worker(worker):
            return
        worker.scene_ready.connect(self._on_scene_ready)
        self._start_thread()

    def _launch_modify(self, prompt):
        """Lance le ModifySceneWorker pour modifier la scene existante"""
        print(f"[WORKER] Lancement ModifySceneWorker | prompt: '{prompt}'")
        worker = ModifySceneWorker(
            prompt,
            self._session.scene_json(),
            self._session.objet_reconnus
        )
        if not self._launch_worker(worker):
            return
        worker.scene_ready.connect(self._on_scene_ready)
        self._start_thread()

    # ------------------------------------------------------------------ #
    #                    CALLBACKS DU PIPELINE                            #
    # ------------------------------------------------------------------ #

    def _cleanup_thread(self):
        """Remet les references thread/worker a None, puis chaine le worker suivant si un intent est en attente."""
        print("[THREAD] Thread termine, nettoyage.")
        self._thread = None
        self._worker = None
        # chainer le worker suivant si IntentWorker a classifie un intent
        if self._pending_intent:
            intent = self._pending_intent
            self._pending_intent = None
            instruction = self._pending_instruction
            if intent == "modify_scene":
                self._launch_modify(instruction)
            else:
                self._launch_recognition(instruction)

    def _on_status_update(self, msg):
        self.status_label.setText(msg)

    def _on_recognition_done(self, objet_reconnus, non_reconnus, alternatives_map):
        """Appele quand la reconnaissance est terminee avec des objets non reconnus"""
        print(f"[RECOGNITION] Reconnus: {list(objet_reconnus.keys())} | Non reconnus: {non_reconnus}")
        # stocker dans la session
        self._session.pending_reconnus = dict(objet_reconnus)
        self._session.pending_unrecognized = list(non_reconnus)
        self._session.alternatives_map = dict(alternatives_map)

        objects_data = objets_list(OBJETS_DIR)

        # afficher les reconnus
        if objet_reconnus:
            noms = ", ".join(objet_reconnus.keys())
            self._append_message(f"Objet(s) reconnu(s) : <b>{html.escape(noms)}</b>", "assistant")

        # afficher les alternatives pour chaque non reconnu
        for label in non_reconnus:
            alts = alternatives_map.get(label, [])
            escaped_label = html.escape(label)
            if alts:
                links = []
                for urdf in alts:
                    name = objects_data[urdf]["name"].strip() if urdf in objects_data else urdf
                    escaped_name = html.escape(name)
                    links.append(
                        f'<a href="resolve:{label}:{urdf}" '
                        f'style="color:#89b4fa; text-decoration:underline; cursor:pointer;">'
                        f'{escaped_name}</a>'
                    )
                links.append(
                    f'<a href="remove:{label}" '
                    f'style="color:#f38ba8; text-decoration:underline; cursor:pointer;">'
                    f'Supprimer</a>'
                )
                options = " | ".join(links)
                self._append_message(
                    f'Objet non reconnu : <b>"{escaped_label}"</b><br>'
                    f'Choisissez une alternative : {options}',
                    "assistant"
                )
            else:
                self._append_message(
                    f'Objet non reconnu : <b>"{escaped_label}"</b> — aucune alternative trouvee.'
                    f' <a href="remove:{label}" style="color:#f38ba8; text-decoration:underline;">'
                    f'Supprimer</a>',
                    "assistant"
                )

        self._session.add_message("assistant", f"Objets non reconnus : {', '.join(non_reconnus)}")

        # si rien n'est reconnu et tout est supprime on affiche une erreur
        if not objet_reconnus and not non_reconnus:
            self._append_message("Aucun objet reconnu dans la description.", "error")

    def _on_link_clicked(self, url):
        """Gere les clics sur les liens de resolution d'objets"""
        link = url.toString()
        print(f"[LINK] Clic : '{link}'")
        objects_data = objets_list(OBJETS_DIR)

        if link.startswith("resolve:"):
            parts = link.split(":", 2)
            if len(parts) == 3:
                _, label, urdf = parts
                if label in self._session.pending_unrecognized and urdf in objects_data:
                    self._session.resolve_object(label, urdf, objects_data)
                    name = objects_data[urdf]["name"].strip()
                    self._append_message(
                        f'"{html.escape(label)}" remplace par <b>{html.escape(name)}</b>',
                        "system"
                    )

        elif link.startswith("remove:"):
            label = link.split(":", 1)[1]
            if label in self._session.pending_unrecognized:
                self._session.remove_object(label)
                self._append_message(
                    f'"{html.escape(label)}" supprime de la scene.',
                    "system"
                )

        # verifier si tous les non reconnus sont resolus
        if self._session.all_resolved():
            if self._session.pending_reconnus:
                self._append_message("Tous les objets resolus. Generation de la scene...", "system")
                self._launch_placement()
            else:
                self._append_message("Aucun objet restant. Veuillez decrire une nouvelle scene.", "error")

    def _on_scene_ready(self, objetsList):
        """Appele quand la scene est prete a afficher"""
        print(f"[SCENE] Scene prete : {[obj.get('id') for obj in objetsList]}")
        self._current_objetsList = objetsList
        self._session.objets_list = objetsList

        # reconstruire objet_reconnus depuis la scene
        objects_data = objets_list(OBJETS_DIR)
        self._session.objet_reconnus = {}
        for obj in objetsList:
            oid = obj.get("id", "")
            urdf = obj.get("urdf", "")
            if urdf in objects_data:
                self._session.objet_reconnus[oid] = {
                    "urdf": urdf,
                    "path": objects_data[urdf]["path"],
                    "dimensions": objects_data[urdf]["dimensions"]
                }

        self.scene_view.update_scene(objetsList)
        names = ", ".join(obj.get("id", "?") for obj in objetsList)
        msg = f"Scene generee avec : {html.escape(names)}."
        self._append_message(msg, "assistant")
        self._session.add_message("assistant", msg)
        self.download_btn.setEnabled(True)
        self.genesis_btn.setEnabled(True)

    def _on_error(self, error_msg):
        self._append_message(html.escape(error_msg), "error")

    def _on_worker_finished(self):
        """Reactive le bouton Envoyer et remet le statut a 'Pret' (sauf si un intent est en attente)."""
        if self._pending_intent:
            return  # le worker suivant sera lance par _cleanup_thread
        self.send_btn.setEnabled(True)
        self.status_label.setText("Pret")
        self.status_label.setStyleSheet("color: #4caf50; font-size: 11px;")

    # ------------------------------------------------------------------ #
    #                    NOUVEAU THREAD / ACTIONS                         #
    # ------------------------------------------------------------------ #

    def _on_load_image(self):
        """Ouvre un sélecteur de fichier image et lance le pipeline V3."""
        if self._thread and self._thread.isRunning():
            QMessageBox.information(self, "En cours", "Generation en cours, veuillez patienter.")
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Choisir une ou plusieurs images", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if not paths:
            return
        names = ", ".join(os.path.basename(p) for p in paths)
        self._append_message(f"Image(s) : <b>{html.escape(names)}</b>", "user")
        self.download_btn.setEnabled(False)
        self.genesis_btn.setEnabled(False)
        worker = ImageSceneWorker(paths)
        if not self._launch_worker(worker):
            return
        worker.scene_ready.connect(self._on_scene_ready)
        self._start_thread()

    def _on_new_thread(self):
        """Reinitialise tout pour une nouvelle conversation"""
        if self._thread and self._thread.isRunning():
            QMessageBox.information(self, "En cours", "Attendez la fin du traitement en cours.")
            return

        self._session.reset()
        self._current_objetsList = None
        self.chat_display.clear()
        self.scene_view.clear()
        self.scene_view._add_ground()
        self.download_btn.setEnabled(False)
        self.genesis_btn.setEnabled(False)
        self.status_label.setText("Pret")
        self.status_label.setStyleSheet("color: #4caf50; font-size: 11px;")
        self._append_message("Nouvelle conversation. Decrivez votre scene.", "system")

    def _on_download_scene(self):
        """Ouvre le 'Enregistrer sous' pour telecharger le JSON de la scene"""
        dest, _ = QFileDialog.getSaveFileName(self, "Enregistrer la scene", "scene.json", "JSON (*.json)")
        if dest:
            try:
                shutil.copy2(SCENE_OUTPUT_FILE, dest)
                self._append_message(f"Scene enregistree : {html.escape(dest)}", "system")
            except Exception as e:
                self._append_message(f"Erreur : {html.escape(str(e))}", "error")

    def _on_launch_genesis(self):
        """Lance genesisdans une autre fenetre"""
        if self._current_objetsList is None:
            return
        launcher = os.path.join(SRC_DIR, "launch_genesis.py")
        try:
            subprocess.Popen(
                [sys.executable, launcher, SCENE_OUTPUT_FILE],
                cwd=SRC_DIR
            )
            self._append_message("Simulation Genesis lancee dans une fenetre separee.", "system")
        except Exception as e:
            self._append_message(f"Impossible de lancer Genesis : {html.escape(str(e))}", "error")

    # ------------------------------------------------------------------ #
    #                             THEME                                  #
    # ------------------------------------------------------------------ #

    def _dark_theme(self):
        """Theme sombre"""
        app = QApplication.instance()

        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#1e1e2e"))
        palette.setColor(QPalette.ColorRole.WindowText,QColor("#cdd6f4"))
        palette.setColor(QPalette.ColorRole.Base, QColor("#181825"))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#1e1e2e"))
        palette.setColor(QPalette.ColorRole.Text,QColor("#cdd6f4"))
        palette.setColor(QPalette.ColorRole.Button, QColor("#313244"))
        palette.setColor(QPalette.ColorRole.ButtonText,QColor("#cdd6f4"))
        palette.setColor(QPalette.ColorRole.Highlight,QColor("#89b4fa"))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#1e1e2e"))
        app.setPalette(palette)

        app.setStyleSheet("""
            QMainWindow, QWidget { background: #1e1e2e; }
            QFrame { border: 1px solid #313244; border-radius: 6px; }

            QPushButton {
                background: #313244; color: #cdd6f4;
                border: 1px solid #45475a; border-radius: 5px;
                padding: 5px 12px;
            }
            QPushButton:hover { background: #45475a; }
            QPushButton:disabled { color: #585b70; background: #1e1e2e; }

            QPushButton#download_btn {
                background: #40a02b; color: white; border: none;
            }
            QPushButton#download_btn:hover { background: #2d7d1e; }
            QPushButton#download_btn:disabled { background: #313244; color: #585b70; }

            QPushButton#genesis_btn {
                background: #1565C0; color: white; border: none;
            }
            QPushButton#genesis_btn:hover { background: #0d47a1; }
            QPushButton#genesis_btn:disabled { background: #313244; color: #585b70; }

            QPushButton#new_thread_btn {
                background: #585b70; color: #cdd6f4; border: none;
                border-radius: 4px; padding: 4px 10px; font-size: 11px;
            }
            QPushButton#new_thread_btn:hover { background: #6c7086; }

            QPushButton#image_btn {
                background: #6c3483; color: white; border: none;
            }
            QPushButton#image_btn:hover { background: #8e44ad; }
            QPushButton#image_btn:disabled { background: #313244; color: #585b70; }

            QLineEdit {
                background: #313244; color: #cdd6f4;
                border: 1px solid #45475a; border-radius: 4px;
                padding: 5px 8px;
            }
            QTextBrowser {
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
