import logging
import json
import requests
import os
import tempfile
import uuid
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QScrollArea,
    QLabel, QGridLayout, QFrame, QCheckBox, QMessageBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap

# Import backend services
from reddit_client import fetch_reddit_memes
from ocr_service import extract_text_from_image, configure_tesseract
from tts_service import TTSManager
from video_compiler import compile_video
from ui_settings_tab import SETTINGS_FILE

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Meme Widget ---
class MemeWidget(QWidget):
    """A widget to display a single meme with a checkbox."""
    def __init__(self, meme_data):
        super().__init__()
        self.meme_data = meme_data
        self.image_path = None

        layout = QVBoxLayout(self)
        self.image_label = QLabel("Downloading...")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setFixedSize(200, 200)
        self.image_label.setStyleSheet("border: 1px solid grey;")

        self.checkbox = QCheckBox(meme_data['title'])
        self.checkbox.setToolTip(meme_data['title'])

        layout.addWidget(self.image_label)
        layout.addWidget(self.checkbox)

    def set_image(self, pixmap):
        self.image_label.setPixmap(pixmap.scaled(
            self.image_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        ))

# --- Worker Threads ---
class RedditSearchWorker(QThread):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, settings, keyword):
        super().__init__()
        self.settings = settings
        self.keyword = keyword

    def run(self):
        try:
            memes = fetch_reddit_memes(
                client_id=self.settings["reddit_client_id"],
                client_secret=self.settings["reddit_client_secret"],
                user_agent=self.settings["reddit_user_agent"],
                keyword=self.keyword
            )
            self.finished.emit(memes)
        except Exception as e:
            logging.error(f"Error in RedditSearchWorker: {e}", exc_info=True)
            self.error.emit(f"Failed to fetch from Reddit: {e}")

class ImageDownloader(QThread):
    finished = pyqtSignal(QPixmap)
    error = pyqtSignal()

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        try:
            response = requests.get(self.url, timeout=10)
            response.raise_for_status()
            pixmap = QPixmap()
            pixmap.loadFromData(response.content)
            self.finished.emit(pixmap)
        except Exception as e:
            logging.error(f"Failed to download image {self.url}: {e}")
            self.error.emit()

import shutil
from youtube_uploader import upload_video

class VideoCompileWorker(QThread):
    finished = pyqtSignal(str, str) # video_path, temp_dir
    error = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, selected_widgets, settings):
        super().__init__()
        self.selected_widgets = selected_widgets
        self.settings = settings

    def run(self):
        temp_dir = tempfile.mkdtemp(prefix="meme-compiler-")
        try:
            self.progress.emit(f"Created temporary directory...")

            if not configure_tesseract(self.settings["tesseract_path"]):
                raise RuntimeError("Tesseract not configured. Check path in Settings.")
            tts_manager = TTSManager(api_key=self.settings["elevenlabs_api_key"])

            processed_meme_data = []
            total_memes = len(self.selected_widgets)

            for i, widget in enumerate(self.selected_widgets):
                self.progress.emit(f"Meme {i+1}/{total_memes}: Downloading image...")
                response = requests.get(widget.meme_data['url'])
                response.raise_for_status()

                ext = os.path.splitext(widget.meme_data['url'])[1] or '.png'
                image_filename = os.path.join(temp_dir, f"img_{i}{ext}")
                with open(image_filename, 'wb') as f: f.write(response.content)

                self.progress.emit(f"Meme {i+1}/{total_memes}: Running OCR...")
                text = extract_text_from_image(image_filename)

                if not text:
                    logging.warning(f"No text for meme {widget.meme_data['title']}.")
                    continue

                self.progress.emit(f"Meme {i+1}/{total_memes}: Generating TTS...")
                audio_filename = os.path.join(temp_dir, f"tts_{i}.mp3")
                tts_manager.generate_tts_audio(text, audio_filename)

                processed_meme_data.append({'image_path': image_filename, 'tts_audio_path': audio_filename})

            if not processed_meme_data:
                raise RuntimeError("No memes with text were found to compile.")

            self.progress.emit("Compiling final video...")
            output_video_path = os.path.join(temp_dir, f"final_video_{uuid.uuid4().hex}.mp4")

            compile_video(
                meme_data=processed_meme_data,
                intro_path=self.settings["intro_path"],
                outro_path=self.settings["outro_path"],
                bg_video_path=self.settings["bg_video_path"],
                bg_music_path=self.settings["bg_music_path"],
                output_path=output_video_path
            )
            self.finished.emit(output_video_path, temp_dir)

        except Exception as e:
            logging.error(f"Error in VideoCompileWorker: {e}", exc_info=True)
            shutil.rmtree(temp_dir) # Clean up on error
            self.error.emit(str(e))

class YouTubeUploadWorker(QThread):
    finished = pyqtSignal(str) # video_id
    error = pyqtSignal(str)

    def __init__(self, settings, video_path, title, description):
        super().__init__()
        self.settings = settings
        self.video_path = video_path
        self.title = title
        self.description = description

    def run(self):
        try:
            video_id = upload_video(
                client_secrets_file=self.settings["google_secrets_path"],
                video_path=self.video_path,
                title=self.title,
                description=self.description,
                tags=["memes", "funny", "reddit"]
            )
            if not video_id:
                raise RuntimeError("Upload failed. Check logs for details.")
            self.finished.emit(video_id)
        except Exception as e:
            self.error.emit(str(e))


# --- Creator Tab ---
class CreatorTab(QWidget):
    def __init__(self):
        super().__init__()
        self.image_downloaders = []

        main_layout = QVBoxLayout(self)

        search_layout = QHBoxLayout()
        self.keyword_input = QLineEdit()
        self.keyword_input.setPlaceholderText("Enter meme keyword...")
        self.search_button = QPushButton("Search / Refresh")
        search_layout.addWidget(self.keyword_input)
        search_layout.addWidget(self.search_button)
        main_layout.addLayout(search_layout)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        self.meme_container = QWidget()
        self.meme_grid_layout = QGridLayout(self.meme_container)
        self.meme_grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll_area.setWidget(self.meme_container)
        main_layout.addWidget(scroll_area)
        self._show_placeholder_message("Enter a keyword to find memes.")

        bottom_layout = QHBoxLayout()
        self.status_label = QLabel("Status: Ready")
        self.compile_button = QPushButton("Compile Selected Memes")
        self.compile_button.setEnabled(False)
        bottom_layout.addWidget(self.status_label, 1)
        bottom_layout.addWidget(self.compile_button)
        main_layout.addLayout(bottom_layout)

        self.search_button.clicked.connect(self._start_search)
        self.compile_button.clicked.connect(self._start_compilation)

    def _load_settings(self):
        try:
            with open(SETTINGS_FILE, 'r') as f: return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError): return None

    def _start_search(self):
        settings = self._load_settings()
        if not settings or not all(settings.get(k) for k in ["reddit_client_id", "reddit_client_secret", "reddit_user_agent"]):
            QMessageBox.warning(self, "Settings Missing", "Please configure Reddit API credentials in Settings.")
            return

        keyword = self.keyword_input.text().strip()
        if not keyword:
            QMessageBox.warning(self, "Keyword Missing", "Please enter a keyword.")
            return

        self.search_button.setEnabled(False)
        self.compile_button.setEnabled(False)
        self.status_label.setText("Status: Searching for memes...")
        self._show_placeholder_message("Searching...")

        self.search_worker = RedditSearchWorker(settings, keyword)
        self.search_worker.finished.connect(self._display_memes)
        self.search_worker.error.connect(self._handle_error)
        self.search_worker.start()

    def _display_memes(self, memes):
        self.search_button.setEnabled(True)
        self._clear_grid()

        if not memes:
            self._show_placeholder_message("No memes found matching your criteria. Try another keyword.")
            self.status_label.setText("Status: No memes found.")
            return

        self.status_label.setText(f"Status: Found {len(memes)} memes. Downloading thumbnails...")
        self.image_downloaders.clear()

        row, col = 0, 0
        for meme_data in memes:
            widget = MemeWidget(meme_data)
            self.meme_grid_layout.addWidget(widget, row, col)

            downloader = ImageDownloader(meme_data['url'])
            downloader.finished.connect(widget.set_image)
            self.image_downloaders.append(downloader)
            downloader.start()

            col += 1
            if col >= 4:
                col = 0
                row += 1

        self.compile_button.setEnabled(True)

    def _start_compilation(self):
        settings = self._load_settings()
        required = ["tesseract_path", "elevenlabs_api_key", "intro_path", "outro_path", "bg_video_path", "bg_music_path"]
        if not settings or not all(settings.get(k) for k in required):
            QMessageBox.warning(self, "Settings Missing", "Please ensure all API keys and file paths are set in Settings.")
            return

        selected_widgets = [self.meme_grid_layout.itemAt(i).widget() for i in range(self.meme_grid_layout.count()) if isinstance(self.meme_grid_layout.itemAt(i).widget(), MemeWidget) and self.meme_grid_layout.itemAt(i).widget().checkbox.isChecked()]

        if not selected_widgets:
            QMessageBox.warning(self, "No Memes Selected", "Please select at least one meme.")
            return

        self.search_button.setEnabled(False)
        self.compile_button.setEnabled(False)

        self.compile_worker = VideoCompileWorker(selected_widgets, settings)
        self.compile_worker.progress.connect(self._update_status)
        self.compile_worker.finished.connect(self._on_compilation_finished)
        self.compile_worker.error.connect(self._handle_error)
        self.compile_worker.start()

    def _on_compilation_finished(self, video_path, temp_dir):
        self._set_ui_enabled(True)
        self.status_label.setText("Status: Ready")

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Compilation Successful!")
        msg_box.setText("Your video has been created.")
        save_button = msg_box.addButton("Save to Device", QMessageBox.ButtonRole.AcceptRole)
        upload_button = msg_box.addButton("Upload to YouTube", QMessageBox.ButtonRole.ActionRole)
        dismiss_button = msg_box.addButton("Dismiss", QMessageBox.ButtonRole.RejectRole)
        msg_box.exec()

        if msg_box.clickedButton() == save_button:
            try:
                dest_path, _ = QFileDialog.getSaveFileName(self, "Save Video", os.path.join(os.path.expanduser("~"), "Downloads", "my_meme_video.mp4"), "MP4 Videos (*.mp4)")
                if dest_path:
                    shutil.move(video_path, dest_path)
                    QMessageBox.information(self, "Success", f"Video saved to {dest_path}")
            except Exception as e:
                self._handle_error(f"Failed to save file: {e}")

        elif msg_box.clickedButton() == upload_button:
            self._start_youtube_upload(video_path)

        # Cleanup the temp directory regardless of choice
        try:
            shutil.rmtree(temp_dir)
            logging.info(f"Successfully cleaned up temporary directory: {temp_dir}")
        except Exception as e:
            logging.error(f"Failed to clean up temporary directory {temp_dir}: {e}")

    def _start_youtube_upload(self, video_path):
        title, ok = QInputDialog.getText(self, "Video Details", "Enter a title for your video:")
        if not ok or not title:
            self.status_label.setText("Status: Upload cancelled.")
            return

        description = "A meme compilation made with Jules' Meme Video Compiler!"
        settings = self._load_settings()

        self._set_ui_enabled(False)
        self.status_label.setText("Status: Uploading to YouTube...")

        self.upload_worker = YouTubeUploadWorker(settings, video_path, title, description)
        self.upload_worker.finished.connect(self._on_upload_finished)
        self.upload_worker.error.connect(self._handle_error)
        self.upload_worker.start()

    def _on_upload_finished(self, video_id):
        self._set_ui_enabled(True)
        self.status_label.setText("Status: Ready")

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Upload Successful!")
        msg_box.setText(f"Successfully uploaded video!\nVideo ID: {video_id}")
        msg_box.setInformativeText(f"Link: https://www.youtube.com/watch?v={video_id}")
        msg_box.exec()

    def _update_status(self, message):
        self.status_label.setText(f"Status: {message}")

    def _handle_error(self, message):
        self._set_ui_enabled(True)
        self.status_label.setText("Status: Error.")
        QMessageBox.critical(self, "An Error Occurred", message)

    def _clear_grid(self):
        while self.meme_grid_layout.count():
            child = self.meme_grid_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _show_placeholder_message(self, message):
        self._clear_grid()
        label = QLabel(message)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("font-size: 16px; color: grey;")
        self.meme_grid_layout.addWidget(label, 0, 0, 1, 4)

    def _set_ui_enabled(self, enabled: bool):
        self.search_button.setEnabled(enabled)
        self.compile_button.setEnabled(enabled)
