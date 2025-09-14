import json
import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit,
    QPushButton, QLabel, QFileDialog, QMessageBox
)
from PyQt6.QtCore import Qt

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

SETTINGS_FILE = "settings.json"

class SettingsTab(QWidget):
    """
    This widget contains the UI for configuring the application's settings.
    """
    def __init__(self):
        super().__init__()

        # --- Main Layout ---
        main_layout = QVBoxLayout(self)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # --- UI Widgets ---
        # API Keys Section
        api_group_label = QLabel("API and Credentials")
        api_group_label.setStyleSheet("font-size: 16px; font-weight: bold; margin-top: 10px;")

        self.reddit_client_id_edit = QLineEdit()
        self.reddit_client_secret_edit = QLineEdit()
        self.reddit_client_secret_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.reddit_user_agent_edit = QLineEdit()
        self.elevenlabs_api_key_edit = QLineEdit()
        self.elevenlabs_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.tesseract_path_edit = QLineEdit()
        tesseract_browse_button = QPushButton("Browse...")
        self.tessdata_path_edit = QLineEdit()
        tessdata_browse_button = QPushButton("Browse...")
        self.google_secrets_path_edit = QLineEdit()
        google_browse_button = QPushButton("Browse...")

        # File Paths Section
        files_group_label = QLabel("Media File Paths")
        files_group_label.setStyleSheet("font-size: 16px; font-weight: bold; margin-top: 20px;")

        self.intro_path_edit = QLineEdit()
        intro_browse_button = QPushButton("Browse...")
        self.outro_path_edit = QLineEdit()
        outro_browse_button = QPushButton("Browse...")
        self.bg_video_path_edit = QLineEdit()
        bg_video_browse_button = QPushButton("Browse...")
        self.bg_music_path_edit = QLineEdit()
        bg_music_browse_button = QPushButton("Browse...")
        self.yt_thumbnail_path_edit = QLineEdit()
        yt_thumbnail_browse_button = QPushButton("Browse...")

        # Save Button
        save_button = QPushButton("Save Settings")
        save_button.setStyleSheet("font-size: 14px; padding: 10px;")

        # --- Form Layout ---
        form_layout = QFormLayout()
        form_layout.addRow(api_group_label)
        form_layout.addRow("Reddit Client ID:", self.reddit_client_id_edit)
        form_layout.addRow("Reddit Client Secret:", self.reddit_client_secret_edit)
        form_layout.addRow("Reddit User Agent:", self.reddit_user_agent_edit)
        form_layout.addRow("ElevenLabs API Key:", self.elevenlabs_api_key_edit)
        form_layout.addRow("Google Client Secrets File:", self._create_browse_row(self.google_secrets_path_edit, google_browse_button))
        form_layout.addRow("Tesseract Executable:", self._create_browse_row(self.tesseract_path_edit, tesseract_browse_button))
        form_layout.addRow("Tessdata Directory:", self._create_browse_row(self.tessdata_path_edit, tessdata_browse_button))

        form_layout.addRow(files_group_label)
        form_layout.addRow("Intro Video:", self._create_browse_row(self.intro_path_edit, intro_browse_button))
        form_layout.addRow("Outro Video:", self._create_browse_row(self.outro_path_edit, outro_browse_button))
        form_layout.addRow("Background Video:", self._create_browse_row(self.bg_video_path_edit, bg_video_browse_button))
        form_layout.addRow("Background Music:", self._create_browse_row(self.bg_music_path_edit, bg_music_browse_button))
        form_layout.addRow("Default YouTube Thumbnail:", self._create_browse_row(self.yt_thumbnail_path_edit, yt_thumbnail_browse_button))

        main_layout.addLayout(form_layout)
        main_layout.addWidget(save_button, 0, Qt.AlignmentFlag.AlignCenter)

        # --- Connect Signals ---
        save_button.clicked.connect(self._save_settings)
        google_browse_button.clicked.connect(self._create_browse_handler(self.google_secrets_path_edit, "JSON files (*.json)"))
        tesseract_browse_button.clicked.connect(self._create_browse_handler(self.tesseract_path_edit, "Executables (*.exe)"))
        tessdata_browse_button.clicked.connect(self._browse_tessdata_directory)
        intro_browse_button.clicked.connect(self._create_browse_handler(self.intro_path_edit, "Videos (*.mp4 *.mov *.avi)"))
        outro_browse_button.clicked.connect(self._create_browse_handler(self.outro_path_edit, "Videos (*.mp4 *.mov *.avi)"))
        bg_video_browse_button.clicked.connect(self._create_browse_handler(self.bg_video_path_edit, "Videos (*.mp4 *.mov *.avi)"))
        bg_music_browse_button.clicked.connect(self._create_browse_handler(self.bg_music_path_edit, "Audio (*.mp3 *.wav)"))
        yt_thumbnail_browse_button.clicked.connect(self._create_browse_handler(self.yt_thumbnail_path_edit, "Images (*.png *.jpg *.jpeg)"))

        # --- Load Existing Settings ---
        self._load_settings()

    def _create_browse_row(self, line_edit, button):
        """Helper to create a horizontal layout for a line edit and a button."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(line_edit)
        layout.addWidget(button)
        return widget

    def _create_browse_handler(self, line_edit_widget, file_filter="All Files (*)"):
        """Creates a closure for handling file browsing."""
        def handler():
            filepath, _ = QFileDialog.getOpenFileName(self, "Select File", "", file_filter)
            if filepath:
                line_edit_widget.setText(filepath)
        return handler

    def _browse_tessdata_directory(self):
        """Opens a dialog to select the tessdata directory."""
        dir_path = QFileDialog.getExistingDirectory(self, "Select Tessdata Directory")
        if dir_path:
            self.tessdata_path_edit.setText(dir_path)

    def _save_settings(self):
        """Saves all settings from the UI to a JSON file."""
        # Load existing settings first to preserve keys not in the UI (like upload_count)
        try:
            with open(SETTINGS_FILE, 'r') as f:
                settings = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            settings = {}

        # Update settings from UI fields
        settings.update({
            "reddit_client_id": self.reddit_client_id_edit.text(),
            "reddit_client_secret": self.reddit_client_secret_edit.text(),
            "reddit_user_agent": self.reddit_user_agent_edit.text(),
            "elevenlabs_api_key": self.elevenlabs_api_key_edit.text(),
            "google_secrets_path": self.google_secrets_path_edit.text(),
            "tesseract_path": self.tesseract_path_edit.text(),
            "tessdata_path": self.tessdata_path_edit.text(),
            "intro_path": self.intro_path_edit.text(),
            "outro_path": self.outro_path_edit.text(),
            "bg_video_path": self.bg_video_path_edit.text(),
            "bg_music_path": self.bg_music_path_edit.text(),
            "yt_thumbnail_path": self.yt_thumbnail_path_edit.text()
        })

        if save_settings(settings):
            QMessageBox.information(self, "Success", "Settings have been saved successfully.")
        else:
            QMessageBox.warning(self, "Error", "Could not save settings.")

    def _load_settings(self):
        """Loads settings from the JSON file and populates the UI."""
        try:
            with open(SETTINGS_FILE, 'r') as f:
                settings = json.load(f)

            self.reddit_client_id_edit.setText(settings.get("reddit_client_id", ""))
            self.reddit_client_secret_edit.setText(settings.get("reddit_client_secret", ""))
            self.reddit_user_agent_edit.setText(settings.get("reddit_user_agent", ""))
            self.elevenlabs_api_key_edit.setText(settings.get("elevenlabs_api_key", ""))
            self.google_secrets_path_edit.setText(settings.get("google_secrets_path", ""))
            self.tesseract_path_edit.setText(settings.get("tesseract_path", ""))
            self.tessdata_path_edit.setText(settings.get("tessdata_path", ""))
            self.intro_path_edit.setText(settings.get("intro_path", ""))
            self.outro_path_edit.setText(settings.get("outro_path", ""))
            self.bg_video_path_edit.setText(settings.get("bg_video_path", ""))
            self.bg_music_path_edit.setText(settings.get("bg_music_path", ""))
            self.yt_thumbnail_path_edit.setText(settings.get("yt_thumbnail_path", ""))
            logging.info(f"Settings loaded from {SETTINGS_FILE}")

        except FileNotFoundError:
            logging.warning(f"{SETTINGS_FILE} not found. Starting with empty settings.")
        except json.JSONDecodeError:
            logging.error(f"Error decoding {SETTINGS_FILE}. The file might be corrupted.")
        except Exception as e:
            logging.error(f"An unexpected error occurred while loading settings: {e}")


def save_settings(settings: dict) -> bool:
    """
    Saves a dictionary of settings to the settings file.

    Args:
        settings (dict): The dictionary of settings to save.

    Returns:
        bool: True if saving was successful, False otherwise.
    """
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=4)
        logging.info(f"Settings successfully saved to {SETTINGS_FILE}")
        return True
    except Exception as e:
        logging.error(f"Failed to save settings: {e}")
        return False
