import logging
import json
import requests
import os
import tempfile
import uuid
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QScrollArea,
    QLabel, QGridLayout, QFrame, QCheckBox, QMessageBox, QInputDialog, QFileDialog, QStyle
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap, QIcon

# Import backend services
from reddit_client import fetch_reddit_memes
from ocr_service import extract_text_from_image, configure_tesseract, configure_tessdata
from tts_service import TTSManager
from video_compiler import compile_video
from ui_settings_tab import SETTINGS_FILE
from ui_voice_dialog import VoiceSelectionDialog

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

from PyQt6.QtWidgets import QDialog

# --- Preview Dialog ---
class PreviewDialog(QDialog):
    """A dialog to show a larger preview of an image."""
    def __init__(self, image_url, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Meme Preview")
        self.setMinimumSize(400, 400)

        self.layout = QVBoxLayout(self)
        self.image_label = QLabel("Downloading high-resolution image...", self)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.image_label)

        self.downloader = ImageDownloader(image_url)
        self.downloader.finished.connect(self.set_image)
        self.downloader.error.connect(self.on_download_error)
        self.downloader.start()

    def set_image(self, pixmap):
        # Get available screen size
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        max_width = int(screen_geometry.width() * 0.9)
        max_height = int(screen_geometry.height() * 0.9)

        # Scale the pixmap to fit within the max dimensions while keeping aspect ratio
        scaled_pixmap = pixmap.scaled(max_width, max_height, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)

        self.image_label.setPixmap(scaled_pixmap)

        # Resize the dialog to fit the scaled image, plus some margin
        self.resize(scaled_pixmap.width() + 20, scaled_pixmap.height() + 20)

    def on_download_error(self):
        self.image_label.setText("Failed to load high-resolution image.")


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

    def on_thumbnail_error(self):
        """Updates the label to show a loading error."""
        self.image_label.setText("Failed to\nload image")
        self.image_label.setStyleSheet("border: 1px solid red; color: red;")

    def mousePressEvent(self, event):
        """Handle clicks on the widget to show a preview."""
        # Trigger preview only if the click is not on the checkbox
        if not self.checkbox.geometry().contains(event.pos()):
            preview_dialog = PreviewDialog(self.meme_data['url'], self)
            preview_dialog.exec()

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
from used_memes_manager import add_used_meme_ids
from ui_upload_dialog import UploadDialog
from ui_settings_tab import save_settings
from ui_transform_dialog import TransformDialog
from utils import crop_to_portrait
from moviepy.editor import VideoFileClip

class VideoCompileWorker(QThread):
    finished = pyqtSignal(str, str, list) # video_path, temp_dir, processed_meme_data
    error = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, meme_configs, settings, voice_id, master_resolution):
        super().__init__()
        self.meme_configs = meme_configs
        self.settings = settings
        self.voice_id = voice_id
        self.master_resolution = master_resolution

    def run(self):
        # The temp dir is now created in _start_compilation, but we need a reference to it
        # This is a bit of a workaround. A better way would be to pass the path.
        # For now, we'll extract it from one of the image paths.
        if not self.meme_configs:
            self.error.emit("No memes to compile.")
            return
        temp_dir = os.path.dirname(self.meme_configs[0]['image_path'])

        try:
            # Configure Tesseract and TTS services
            configure_tessdata(self.settings.get("tessdata_path"))
            if not configure_tesseract(self.settings.get("tesseract_path")):
                raise RuntimeError("Tesseract executable not configured. Check path in Settings.")
            tts_manager = TTSManager(api_key=self.settings.get("elevenlabs_api_key"))

            processed_meme_data = []
            total_memes = len(self.meme_configs)

            for i, config in enumerate(self.meme_configs):
                self.progress.emit(f"Meme {i+1}/{total_memes}: Running OCR...")
                text = extract_text_from_image(config['image_path'])

                if not text:
                    logging.warning(f"No text for meme {config['title']}. Skipping.")
                    # Still include it in the video, just without audio
                    config['tts_audio_path'] = None
                    processed_meme_data.append(config)
                    continue

                self.progress.emit(f"Meme {i+1}/{total_memes}: Generating TTS...")
                audio_filename = os.path.join(temp_dir, f"tts_{i}.mp3")
                tts_manager.generate_tts_audio(
                    text_to_speak=text,
                    output_filepath=audio_filename,
                    voice=self.voice_id
                )

                config['tts_audio_path'] = audio_filename
                processed_meme_data.append(config)

            if not processed_meme_data:
                self.error.emit("Compilation failed: No memes were processed.")
                return

            self.progress.emit("Compiling final video...")
            output_video_path = os.path.join(temp_dir, f"final_video_{uuid.uuid4().hex}.mp4")

            result_path = compile_video(
                meme_data=processed_meme_data,
                master_resolution=self.master_resolution,
                intro_path=self.settings["intro_path"],
                outro_path=self.settings["outro_path"],
                bg_video_path=self.settings["bg_video_path"],
                bg_music_path=self.settings["bg_music_path"],
                output_path=output_video_path
            )

            if result_path:
                self.finished.emit(output_video_path, temp_dir, processed_meme_data)
            else:
                raise RuntimeError("Video compilation failed. Check logs for details.")

        except Exception as e:
            logging.error(f"Error in VideoCompileWorker: {e}", exc_info=True)
            shutil.rmtree(temp_dir) # Clean up on error
            self.error.emit(str(e))

class YouTubeUploadWorker(QThread):
    finished = pyqtSignal(str, list) # video_id, used_meme_data
    error = pyqtSignal(str)

    def __init__(self, settings, video_path, upload_details, meme_data, temp_dir):
        super().__init__()
        self.settings = settings
        self.video_path = video_path
        self.upload_details = upload_details
        self.meme_data = meme_data
        self.temp_dir = temp_dir

    def run(self):
        try:
            video_id = upload_video(
                client_secrets_file=self.settings.get("google_secrets_path"),
                video_path=self.video_path,
                title=self.upload_details["title"],
                description=self.upload_details["description"],
                tags=self.upload_details["tags"],
                privacy_status=self.upload_details["privacy"],
                thumbnail_path=self.upload_details.get("thumbnail_path")
            )
            if not video_id:
                raise RuntimeError("Upload failed. Check logs for details.")
            self.finished.emit(video_id, self.meme_data)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            # Clean up the temporary directory after the upload attempt
            try:
                shutil.rmtree(self.temp_dir)
                logging.info(f"Successfully cleaned up temporary directory: {self.temp_dir}")
            except Exception as e:
                logging.error(f"Failed to clean up temporary directory {self.temp_dir}: {e}")

class FetchSubscriptionInfoWorker(QThread):
    """Worker thread to fetch ElevenLabs subscription info."""
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, api_key):
        super().__init__()
        self.api_key = api_key

    def run(self):
        try:
            tts_manager = TTSManager(api_key=self.api_key)
            info = tts_manager.get_subscription_info()
            self.finished.emit(info)
        except Exception as e:
            self.error.emit(f"Failed to fetch subscription info: {e}")

class FetchVoicesWorker(QThread):
    """Worker thread to fetch available voices from ElevenLabs."""
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, api_key):
        super().__init__()
        self.api_key = api_key

    def run(self):
        try:
            tts_manager = TTSManager(api_key=self.api_key)
            voices = tts_manager.get_available_voices()
            self.finished.emit(voices)
        except Exception as e:
            self.error.emit(f"Failed to fetch voices: {e}")


# --- Creator Tab ---
class CreatorTab(QWidget):
    def __init__(self):
        super().__init__()
        self.image_downloaders = []
        self.widgets_for_compilation = []
        self.last_compilation_data = []

        main_layout = QVBoxLayout(self)

        search_layout = QHBoxLayout()
        self.keyword_input = QLineEdit()
        self.keyword_input.setPlaceholderText("Enter meme keyword...")
        self.search_button = QPushButton("Search / Refresh")
        search_layout.addWidget(self.keyword_input)
        search_layout.addWidget(self.search_button)

        # --- Quota Display ---
        quota_layout = QHBoxLayout()
        self.quota_label = QLabel("ElevenLabs Quota: N/A")
        self.refresh_quota_button = QPushButton()
        # Using a standard, built-in icon for refresh
        self.refresh_quota_button.setIcon(self.style().standardIcon(getattr(QStyle.StandardPixmap, "SP_BrowserReload")))
        self.refresh_quota_button.setToolTip("Refresh character quota")
        quota_layout.addStretch()
        quota_layout.addWidget(self.quota_label)
        quota_layout.addWidget(self.refresh_quota_button)

        main_layout.addLayout(search_layout)
        main_layout.addLayout(quota_layout)

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
        self.refresh_quota_button.clicked.connect(self._update_character_count)

        # Initial load of character count
        self._update_character_count()

    def _update_character_count(self):
        """Starts the worker to fetch the latest subscription info."""
        settings = self._load_settings()
        if settings and settings.get("elevenlabs_api_key"):
            self.refresh_quota_button.setEnabled(False)
            self.sub_info_worker = FetchSubscriptionInfoWorker(settings["elevenlabs_api_key"])
            self.sub_info_worker.finished.connect(self._on_subscription_info_fetched)
            self.sub_info_worker.error.connect(self._handle_error) # Can reuse the generic error handler
            self.sub_info_worker.start()
        else:
            self.quota_label.setText("ElevenLabs Quota: API Key not set.")

    def _on_subscription_info_fetched(self, info):
        """Updates the quota label with the fetched info."""
        self.refresh_quota_button.setEnabled(True)
        if info:
            used = info.get("character_count", 0)
            limit = info.get("character_limit", 0)
            self.quota_label.setText(f"ElevenLabs Quota: {used:,}/{limit:,} characters used.")
        else:
            self.quota_label.setText("ElevenLabs Quota: Failed to fetch.")

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
            downloader.error.connect(widget.on_thumbnail_error)
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

        # --- New Dynamic Resolution Workflow ---
        temp_dir = tempfile.mkdtemp(prefix="meme-compiler-")
        try:
            # 1. Determine Master Resolution from Intro
            self.status_label.setText("Status: Analyzing intro video...")
            intro_clip = VideoFileClip(settings["intro_path"])
            cropped_intro = crop_to_portrait(intro_clip)
            master_resolution = cropped_intro.size
            intro_clip.close()
            cropped_intro.close()
            logging.info(f"Master resolution set to {master_resolution} based on intro.")

            # 2. Loop through memes for user transform
            meme_configs = []
            for i, widget in enumerate(selected_widgets):
                self.status_label.setText(f"Status: Downloading image {i+1}/{len(selected_widgets)} for positioning...")

                response = requests.get(widget.meme_data['url'])
                response.raise_for_status()
                ext = os.path.splitext(widget.meme_data['url'])[1] or '.png'
                image_path = os.path.join(temp_dir, f"img_{i}{ext}")
                with open(image_path, 'wb') as f:
                    f.write(response.content)

                self.status_label.setText(f"Status: Awaiting position for meme {i+1}...")
                transform_dialog = TransformDialog(image_path, master_resolution, self)
                if transform_dialog.exec() == QDialog.DialogCode.Accepted:
                    transform_data = transform_dialog.get_transform()
                    config = widget.meme_data.copy()
                    config['image_path'] = image_path
                    config['transform'] = transform_data
                    meme_configs.append(config)
                else:
                    self.status_label.setText("Status: Compilation cancelled.")
                    shutil.rmtree(temp_dir)
                    self._set_ui_enabled(True)
                    return

            # 3. Proceed to voice selection
            self.settings = settings
            self.meme_configs_for_compilation = meme_configs
            self.master_resolution_for_compilation = master_resolution
            self.status_label.setText("Status: Fetching available voices...")
            self.fetch_voices_worker = FetchVoicesWorker(api_key=self.settings.get("elevenlabs_api_key"))
            self.fetch_voices_worker.finished.connect(self._on_voices_fetched)
            self.fetch_voices_worker.error.connect(self._handle_error)
            self.fetch_voices_worker.start()

        except Exception as e:
            self._handle_error(f"Failed during pre-compilation setup: {e}")
            if 'temp_dir' in locals() and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

    def _on_voices_fetched(self, voices):
        """Handles the fetched voices and opens the selection dialog."""
        if not voices:
            self._handle_error("Could not retrieve any voices from ElevenLabs. Please check your API key.")
            return

        dialog = VoiceSelectionDialog(voices, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected_voice_id = dialog.get_selected_voice_id()
            if selected_voice_id:
                self.status_label.setText("Status: Starting compilation...")
                # Now start the actual video compilation with all the final data
                self.compile_worker = VideoCompileWorker(
                    self.meme_configs_for_compilation,
                    self.settings,
                    selected_voice_id,
                    self.master_resolution_for_compilation
                )
                self.compile_worker.progress.connect(self._update_status)
                self.compile_worker.finished.connect(self._on_compilation_finished)
                self.compile_worker.error.connect(self._handle_error)
                self.compile_worker.start()
        else:
            self.status_label.setText("Status: Compilation cancelled.")
            self._set_ui_enabled(True)


    def _on_compilation_finished(self, video_path, temp_dir, processed_meme_data):
        self.last_compilation_data = processed_meme_data
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
            meme_data_list = [w.meme_data for w in self.widgets_for_compilation]
            self._start_youtube_upload(video_path, meme_data_list, temp_dir)
        else:
            # If user dismisses or saves, clean up the temp dir
            try:
                shutil.rmtree(temp_dir)
                logging.info(f"Successfully cleaned up temporary directory: {temp_dir}")
            except Exception as e:
                logging.error(f"Failed to clean up temporary directory {temp_dir}: {e}")

    def _start_youtube_upload(self, video_path, meme_data_list, temp_dir):
        settings = self._load_settings()
        if not settings:
            self._handle_error("Settings not found. Please configure the application.")
            return

        # Automatic thumbnail logic
        thumbnail_to_upload = settings.get("yt_thumbnail_path")
        if not thumbnail_to_upload and self.last_compilation_data:
            # Use the first processed meme image as a fallback thumbnail
            thumbnail_to_upload = self.last_compilation_data[0].get('image_path')
            logging.info(f"No default thumbnail set. Using first meme as fallback: {thumbnail_to_upload}")

        upload_count = settings.get('upload_count', 0)

        upload_dialog = UploadDialog(upload_count, self)
        if upload_dialog.exec() == QDialog.DialogCode.Accepted:
            upload_details = upload_dialog.get_upload_details()

            self._set_ui_enabled(False)
            self.status_label.setText("Status: Uploading to YouTube...")

            # Add the chosen thumbnail path to the details passed to the worker
            upload_details['thumbnail_path'] = thumbnail_to_upload

            self.upload_worker = YouTubeUploadWorker(settings, video_path, upload_details, meme_data_list, temp_dir)
            self.upload_worker.finished.connect(self._on_upload_finished)
            self.upload_worker.error.connect(self._handle_error)
            self.upload_worker.start()
        else:
            # If user cancels the upload dialog, clean up
            self.status_label.setText("Status: Upload cancelled.")
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logging.error(f"Failed to clean up temp dir after cancelled upload: {e}")

    def _on_upload_finished(self, video_id, used_meme_data):
        self._set_ui_enabled(True)
        self.status_label.setText("Status: Ready")

        # Log the used meme IDs
        meme_ids_to_log = [meme['id'] for meme in used_meme_data]
        add_used_meme_ids(meme_ids_to_log)

        # Increment and save the upload count
        settings = self._load_settings()
        if settings:
            current_count = settings.get('upload_count', 0)
            settings['upload_count'] = current_count + 1
            save_settings(settings)

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

    def shutdown_workers(self):
        """Safely terminates any running worker threads."""
        logging.info("Shutdown initiated. Terminating active worker threads...")
        workers = [
            getattr(self, 'search_worker', None),
            getattr(self, 'compile_worker', None),
            getattr(self, 'upload_worker', None)
        ]
        workers.extend(self.image_downloaders)

        for worker in workers:
            if worker is not None and worker.isRunning():
                try:
                    worker.quit()
                    worker.wait(2000) # Wait up to 2 seconds
                    logging.info(f"Terminated worker: {worker.__class__.__name__}")
                except Exception as e:
                    logging.error(f"Error terminating worker {worker.__class__.__name__}: {e}")
