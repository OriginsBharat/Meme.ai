import logging
import json
import requests
import os
import tempfile
import uuid
import shutil
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QScrollArea,
    QLabel, QGridLayout, QFrame, QCheckBox, QMessageBox, QFileDialog, QStyle, QDialog
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap

# --- Re-organized and cleaned imports ---
from reddit_client import fetch_reddit_memes
from x_client import fetch_x_memes
from ocr_service import extract_text_from_image, configure_tesseract, configure_tessdata
from tts_service import TTSManager
from video_compiler import compile_video
from youtube_uploader import upload_video
from used_memes_manager import add_used_meme_ids
from ui_settings_tab import SETTINGS_FILE, save_settings
from ui_voice_dialog import VoiceSelectionDialog
from ui_transform_dialog import TransformDialog
from ui_ocr_edit_dialog import OcrEditDialog

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        max_width = int(screen_geometry.width() * 0.9)
        max_height = int(screen_geometry.height() * 0.9)
        scaled_pixmap = pixmap.scaled(max_width, max_height, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.image_label.setPixmap(scaled_pixmap)
        self.resize(scaled_pixmap.width() + 20, scaled_pixmap.height() + 20)

    def on_download_error(self):
        self.image_label.setText("Failed to load high-resolution image.")

# --- Meme Widget ---
class MemeWidget(QWidget):
    """A widget to display a single meme with a checkbox."""
    def __init__(self, meme_data):
        super().__init__()
        self.meme_data = meme_data

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
        self.image_label.setText("Failed to\nload image")
        self.image_label.setStyleSheet("border: 1px solid red; color: red;")

    def mousePressEvent(self, event):
        if not self.checkbox.geometry().contains(event.pos()):
            preview_dialog = PreviewDialog(self.meme_data['url'], self)
            preview_dialog.exec()

class PreprocessingWorker(QThread):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)
    progress = pyqtSignal(str, int, int) # message, current, total

    def __init__(self, meme_configs, temp_dir):
        super().__init__()
        self.meme_configs = meme_configs
        self.temp_dir = temp_dir

    def run(self):
        try:
            processed_configs = []
            total = len(self.meme_configs)
            for i, config in enumerate(self.meme_configs):
                self.progress.emit(f"Downloading {config['title'][:30]}...", i + 1, total)

                # Download image
                response = requests.get(config['url'])
                response.raise_for_status()
                ext = os.path.splitext(config['url'])[1] or '.png'
                image_path = os.path.join(self.temp_dir, f"img_{uuid.uuid4().hex}{ext}")
                with open(image_path, 'wb') as f:
                    f.write(response.content)
                config['image_path'] = image_path

                # Run OCR
                self.progress.emit(f"Running OCR on {config['title'][:30]}...", i + 1, total)
                extracted_text = extract_text_from_image(image_path)
                config['extracted_text'] = extracted_text

                processed_configs.append(config)

            self.finished.emit(processed_configs)

        except Exception as e:
            logging.error(f"Error during preprocessing: {e}", exc_info=True)
            self.error.emit(f"Failed during preprocessing: {e}")

# --- Worker Threads ---
class SearchWorker(QThread):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, settings, keyword, source):
        super().__init__()
        self.settings = settings
        self.keyword = keyword
        self.source = source

    def run(self):
        try:
            all_memes = []
            if self.source in ["reddit", "both"]:
                logging.info("Fetching memes from Reddit...")
                reddit_memes = fetch_reddit_memes(
                    client_id=self.settings["reddit_client_id"],
                    client_secret=self.settings["reddit_client_secret"],
                    user_agent=self.settings["reddit_user_agent"],
                    keyword=self.keyword
                )
                all_memes.extend(reddit_memes)

            if self.source in ["x", "both"]:
                logging.info("Fetching memes from X/Twitter...")
                x_memes = fetch_x_memes(
                    username=self.settings["x_username"],
                    password=self.settings["x_password"],
                    keyword=self.keyword
                )
                all_memes.extend(x_memes)

            # Shuffle the combined list to mix sources
            random.shuffle(all_memes)

            self.finished.emit(all_memes)
        except Exception as e:
            logging.error(f"Error in SearchWorker: {e}", exc_info=True)
            self.error.emit(f"Failed to fetch memes: {e}")

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

class VideoCompileWorker(QThread):
    finished = pyqtSignal(str, str, list) # video_path, temp_dir, processed_meme_data
    error = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, meme_configs, settings, voice_id):
        super().__init__()
        self.meme_configs = meme_configs
        self.settings = settings
        self.voice_id = voice_id

    def run(self):
        if not self.meme_configs:
            self.error.emit("No memes to compile.")
            return

        first_item = self.meme_configs[0]
        if 'image_path' in first_item:
            temp_dir = os.path.dirname(first_item['image_path'])
        else:
            self.error.emit("Could not determine temporary directory from first meme config.")
            return

        try:
            output_video_path = os.path.join(temp_dir, f"final_video_{uuid.uuid4().hex}.mp4")

            # --- Image Mode TTS Generation ---
            self.progress.emit("Generating TTS audio...")
            tts_manager = TTSManager(api_key=self.settings.get("elevenlabs_api_key"))
            processed_data = []
            for config in self.meme_configs:
                if config.get('text'):
                    audio_filename = os.path.join(temp_dir, f"tts_{uuid.uuid4().hex}.mp3")
                    tts_manager.generate_tts_audio(
                        text_to_speak=config['text'],
                        output_filepath=audio_filename,
                        voice=self.voice_id
                    )
                    config['tts_audio_path'] = audio_filename
                processed_data.append(config)

            # --- Image Mode Compilation ---
            self.progress.emit("Compiling video...")
            result_path = compile_video(
                meme_data=processed_data,
                intro_path=self.settings["intro_path"],
                outro_path=self.settings["outro_path"],
                bg_video_path=self.settings["bg_video_path"],
                bg_music_path=self.settings["bg_music_path"],
                output_path=output_video_path
            )

            if result_path:
                self.finished.emit(output_video_path, temp_dir, processed_data)
            else:
                raise RuntimeError("Video compilation failed. Check logs for details.")

        except Exception as e:
            logging.error(f"Error in VideoCompileWorker: {e}", exc_info=True)
            if 'temp_dir' in locals() and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
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
            try:
                shutil.rmtree(self.temp_dir)
                logging.info(f"Successfully cleaned up temporary directory: {self.temp_dir}")
            except Exception as e:
                logging.error(f"Failed to clean up temporary directory {self.temp_dir}: {e}")

class FetchSubscriptionInfoWorker(QThread):
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
import random
from PyQt6.QtWidgets import QGroupBox, QRadioButton

class CreatorTab(QWidget):
    def __init__(self):
        super().__init__()
        self.image_downloaders = []
        self.last_compilation_data = []
        self.current_source = "reddit" # Default source

        main_layout = QVBoxLayout(self)

        # --- Search ---
        search_layout = QHBoxLayout()
        self.keyword_input = QLineEdit()
        self.keyword_input.setPlaceholderText("Enter meme keyword...")
        self.search_button = QPushButton("Search")
        search_layout.addWidget(self.keyword_input)
        search_layout.addWidget(self.search_button)

        # --- Source Selection ---
        source_group_box = QGroupBox("Meme Source")
        source_layout = QHBoxLayout()
        self.reddit_radio = QRadioButton("Reddit")
        self.x_radio = QRadioButton("X")
        self.both_radio = QRadioButton("Both")
        self.reddit_radio.setChecked(True)

        self.reddit_radio.toggled.connect(lambda: self._source_changed("reddit"))
        self.x_radio.toggled.connect(lambda: self._source_changed("x"))
        self.both_radio.toggled.connect(lambda: self._source_changed("both"))

        source_layout.addWidget(self.reddit_radio)
        source_layout.addWidget(self.x_radio)
        source_layout.addWidget(self.both_radio)
        source_layout.addStretch()
        source_group_box.setLayout(source_layout)

        # --- Quota Display ---
        quota_layout = QHBoxLayout()
        self.quota_label = QLabel("ElevenLabs Quota: N/A")
        self.refresh_quota_button = QPushButton()
        self.refresh_quota_button.setIcon(self.style().standardIcon(getattr(QStyle.StandardPixmap, "SP_BrowserReload")))
        self.refresh_quota_button.setToolTip("Refresh character quota")
        quota_layout.addStretch()
        quota_layout.addWidget(self.quota_label)
        quota_layout.addWidget(self.refresh_quota_button)

        main_layout.addLayout(search_layout)
        main_layout.addWidget(source_group_box)
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

        self._update_character_count()

    def _update_character_count(self):
        settings = self._load_settings()
        if settings and settings.get("elevenlabs_api_key"):
            self.refresh_quota_button.setEnabled(False)
            self.sub_info_worker = FetchSubscriptionInfoWorker(settings["elevenlabs_api_key"])
            self.sub_info_worker.finished.connect(self._on_subscription_info_fetched)
            self.sub_info_worker.error.connect(self._handle_error)
            self.sub_info_worker.start()
        else:
            self.quota_label.setText("ElevenLabs Quota: API Key not set.")

    def _on_subscription_info_fetched(self, info):
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

    def _source_changed(self, source):
        if self.sender().isChecked():
            self.current_source = source
            logging.info(f"Meme source changed to: {self.current_source}")
            self._clear_grid()
            self._show_placeholder_message(f"Source set to {source.capitalize()}. Enter a keyword to search.")

    def _start_search(self):
        settings = self._load_settings()
        if not settings:
            QMessageBox.warning(self, "Settings Missing", "Please configure your settings first.")
            return

        # Validate credentials based on selected source
        if self.current_source in ["reddit", "both"]:
            if not all(settings.get(k) for k in ["reddit_client_id", "reddit_client_secret", "reddit_user_agent"]):
                QMessageBox.warning(self, "Reddit Settings Missing", "Please configure Reddit API credentials in Settings to use this source.")
                return
        if self.current_source in ["x", "both"]:
            if not all(settings.get(k) for k in ["x_username", "x_password"]):
                QMessageBox.warning(self, "X/Twitter Settings Missing", "Please configure your X/Twitter username and password in Settings to use this source.")
                return

        keyword = self.keyword_input.text().strip()
        if not keyword:
            QMessageBox.warning(self, "Keyword Missing", "Please enter a keyword.")
            return

        self._set_ui_enabled(False)
        self.status_label.setText(f"Status: Searching {self.current_source.capitalize()} for '{keyword}'...")
        self._clear_grid()
        self._show_placeholder_message("Searching for new memes...")

        self.search_worker = SearchWorker(settings, keyword, self.current_source)
        self.search_worker.finished.connect(self._display_memes)
        self.search_worker.error.connect(self._handle_error)
        self.search_worker.start()

    def _display_memes(self, memes):
        self._set_ui_enabled(True)
        self._clear_grid()

        if not memes:
            self._show_placeholder_message("No memes found matching your criteria. Try another keyword.")
            self.status_label.setText("Status: No memes found.")
            return

        self.status_label.setText(f"Status: Displaying {len(memes)} memes. Downloading thumbnails...")
        self.image_downloaders.clear()

        num_cols = 4
        for i, meme_data in enumerate(memes):
            widget = MemeWidget(meme_data)
            row = i // num_cols
            col = i % num_cols
            self.meme_grid_layout.addWidget(widget, row, col)

            thumbnail_url = meme_data.get('thumbnail_url')
            if not thumbnail_url or thumbnail_url in ['self', 'default', 'nsfw']:
                thumbnail_url = "https://www.redditstatic.com/icon.png"

            downloader = ImageDownloader(thumbnail_url)
            downloader.finished.connect(widget.set_image)
            downloader.error.connect(widget.on_thumbnail_error)
            self.image_downloaders.append(downloader)
            downloader.start()

        self.compile_button.setEnabled(True)
        self.status_label.setText("Status: Ready")

    def _start_compilation(self):
        settings = self._load_settings()
        required = ["tesseract_path", "elevenlabs_api_key", "intro_path", "outro_path", "bg_video_path", "bg_music_path"]
        if not settings or not all(settings.get(k) for k in required):
            QMessageBox.warning(self, "Settings Missing", "Please ensure all API keys and file paths are set in Settings.")
            return

        selected_widgets = [w for w in self.findChildren(MemeWidget) if w.checkbox.isChecked()]
        if not selected_widgets:
            QMessageBox.warning(self, "No Memes Selected", "Please select at least one meme.")
            return

        configure_tessdata(settings.get("tessdata_path"))
        if not configure_tesseract(settings.get("tesseract_path")):
            self._handle_error("Tesseract executable not configured. Check path in Settings.")
            return

        self._set_ui_enabled(False)
        self.temp_dir = tempfile.mkdtemp(prefix="meme-compiler-")

        meme_configs_to_process = [w.meme_data.copy() for w in selected_widgets]

        self.status_label.setText("Status: Preprocessing memes...")
        self.preprocess_worker = PreprocessingWorker(meme_configs_to_process, self.temp_dir)
        self.preprocess_worker.finished.connect(self._on_preprocessing_finished)
        self.preprocess_worker.progress.connect(self._update_preprocess_progress)
        self.preprocess_worker.error.connect(self._handle_error)
        self.preprocess_worker.start()

    def _update_preprocess_progress(self, message, current, total):
        self.status_label.setText(f"Status: ({current}/{total}) {message}")

    def _on_preprocessing_finished(self, preprocessed_configs):
        try:
            final_meme_configs = []
            for config in preprocessed_configs:
                # --- Interactive Dialogs on Main Thread ---
                transform_dialog = TransformDialog(config['image_path'], self)
                if transform_dialog.exec() != QDialog.DialogCode.Accepted:
                    raise InterruptedError("Compilation cancelled by user.")
                config['transform'] = transform_dialog.get_transform()

                ocr_dialog = OcrEditDialog(config['extracted_text'], self)
                if ocr_dialog.exec() != QDialog.DialogCode.Accepted:
                    raise InterruptedError("Compilation cancelled by user.")
                config['text'] = ocr_dialog.get_text()

                final_meme_configs.append(config)

            if not final_meme_configs:
                raise ValueError("No valid memes were processed for compilation.")

            # --- Continue to Voice Selection ---
            self.settings = self._load_settings()
            self.meme_configs_for_compilation = final_meme_configs

            self.status_label.setText("Fetching available voices...")
            self.fetch_voices_worker = FetchVoicesWorker(api_key=self.settings.get("elevenlabs_api_key"))
            self.fetch_voices_worker.finished.connect(self._on_voices_fetched)
            self.fetch_voices_worker.error.connect(self._handle_error)
            self.fetch_voices_worker.start()

        except InterruptedError as e:
            self.status_label.setText(f"Status: {e}")
            shutil.rmtree(self.temp_dir)
            self._set_ui_enabled(True)
        except Exception as e:
            self._handle_error(f"Failed during interactive setup: {e}")
            if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)

    def _on_voices_fetched(self, voices):
        if not voices:
            self._handle_error("Could not retrieve any voices from ElevenLabs. Please check your API key.")
            return

        dialog = VoiceSelectionDialog(voices, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected_voice_id = dialog.get_selected_voice_id()
            if selected_voice_id:
                self.status_label.setText("Status: Starting compilation...")
                self.compile_worker = VideoCompileWorker(
                    self.meme_configs_for_compilation,
                    self.settings,
                    selected_voice_id
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

        clicked_button = msg_box.clickedButton()
        if clicked_button == save_button:
            try:
                dest_path, _ = QFileDialog.getSaveFileName(self, "Save Video", os.path.join(os.path.expanduser("~"), "Downloads", "my_meme_video.mp4"), "MP4 Videos (*.mp4)")
                if dest_path:
                    shutil.move(video_path, dest_path)
                    QMessageBox.information(self, "Success", f"Video saved to {dest_path}")
            except Exception as e:
                self._handle_error(f"Failed to save file: {e}")

        elif clicked_button == upload_button:
            self._start_youtube_upload(video_path, processed_meme_data, temp_dir)
            return # The upload worker will handle temp dir cleanup

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

        thumbnail_to_upload = settings.get("yt_thumbnail_path")
        if not thumbnail_to_upload and self.last_compilation_data:
            thumbnail_to_upload = self.last_compilation_data[0].get('image_path')
            logging.info(f"No default thumbnail set. Using first meme as fallback: {thumbnail_to_upload}")

        upload_count = settings.get('upload_count', 0)

        upload_dialog = UploadDialog(upload_count, self)
        if upload_dialog.exec() == QDialog.DialogCode.Accepted:
            upload_details = upload_dialog.get_upload_details()
            upload_details['thumbnail_path'] = thumbnail_to_upload

            self._set_ui_enabled(False)
            self.status_label.setText("Status: Uploading to YouTube...")

            self.upload_worker = YouTubeUploadWorker(settings, video_path, upload_details, meme_data_list, temp_dir)
            self.upload_worker.finished.connect(self._on_upload_finished)
            self.upload_worker.error.connect(self._handle_error)
            self.upload_worker.start()
        else:
            self.status_label.setText("Status: Upload cancelled.")
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logging.error(f"Failed to clean up temp dir after cancelled upload: {e}")

    def _on_upload_finished(self, video_id, used_meme_data):
        self._set_ui_enabled(True)
        self.status_label.setText("Status: Ready")

        meme_ids_to_log = [meme['id'] for meme in used_meme_data]
        add_used_meme_ids(meme_ids_to_log)

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
        self.refresh_quota_button.setEnabled(enabled)

    def shutdown_workers(self):
        logging.info("Shutdown initiated. Terminating active worker threads...")
        workers = [
            getattr(self, 'search_worker', None),
            getattr(self, 'compile_worker', None),
            getattr(self, 'upload_worker', None),
            getattr(self, 'sub_info_worker', None),
            getattr(self, 'fetch_voices_worker', None)
        ]
        workers.extend(self.image_downloaders)

        for worker in workers:
            if worker is not None and worker.isRunning():
                try:
                    worker.quit()
                    worker.wait(2000)
                    logging.info(f"Terminated worker: {worker.__class__.__name__}")
                except Exception as e:
                    logging.error(f"Error terminating worker {worker.__class__.__name__}: {e}")