import logging
import json
import requests
import os
import tempfile
import uuid
import shutil
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QScrollArea,
    QLabel, QGridLayout, QFrame, QCheckBox, QMessageBox, QInputDialog, QFileDialog, QStyle
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QPixmap, QIcon

# Import backend services
from reddit_client import fetch_reddit_memes
from ocr_service import extract_text_from_image, configure_tesseract, configure_tessdata
from tts_service import TTSManager
from video_compiler import compile_video
from ui_settings_tab import SETTINGS_FILE
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

from youtube_uploader import upload_video
from used_memes_manager import add_used_meme_ids
from ui_upload_dialog import UploadDialog
from ui_settings_tab import save_settings
from ui_transform_dialog import TransformDialog
from ui_ocr_edit_dialog import OcrEditDialog
from video_downloader import download_video
from moviepy.editor import VideoFileClip

class VideoCompileWorker(QThread):
    finished = pyqtSignal(str, str, list) # video_path, temp_dir, processed_meme_data
    error = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, meme_configs, settings, voice_id, mode='image'):
        super().__init__()
        self.meme_configs = meme_configs
        self.settings = settings
        self.voice_id = voice_id
        self.mode = mode

    def run(self):
        if not self.meme_configs:
            self.error.emit("No memes to compile.")
            return

        # This logic is brittle, but we're keeping it for now. It requires that the
        # _start_compilation method ensures at least one item has a downloadable path.
        first_item = self.meme_configs[0]
        if 'image_path' in first_item:
            temp_dir = os.path.dirname(first_item['image_path'])
        elif 'video_path' in first_item:
            temp_dir = os.path.dirname(first_item['video_path'])
        else:
            self.error.emit("Could not determine temporary directory from first meme config.")
            return

        try:
            output_video_path = os.path.join(temp_dir, f"final_video_{uuid.uuid4().hex}.mp4")
            processed_data = self.meme_configs

            if self.mode == 'image':
                self.progress.emit("Generating TTS audio for image memes...")
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

                self.progress.emit("Compiling overlay-style video...")
                result_path = compile_video(
                    meme_data=processed_data,
                    intro_path=self.settings["intro_path"],
                    outro_path=self.settings["outro_path"],
                    bg_video_path=self.settings["bg_video_path"],
                    bg_music_path=self.settings["bg_music_path"],
                    output_path=output_video_path
                )

            elif self.mode == 'video':
                self.progress.emit("Compiling full-screen video...")
                video_paths = [config['video_path'] for config in self.meme_configs if 'video_path' in config]
                result_path = compile_video_fullscreen(
                    video_paths=video_paths,
                    intro_path=self.settings["intro_path"],
                    outro_path=self.settings["outro_path"],
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

        # State for paginated Reddit search
        self.last_keyword_searched = ""
        self.last_post_fullname = None
        self.current_mode = "image"

        main_layout = QVBoxLayout(self)

        # --- Search and Mode Selection ---
        search_layout = QHBoxLayout()
        self.keyword_input = QLineEdit()
        self.keyword_input.setPlaceholderText("Enter meme keyword...")
        self.search_button = QPushButton("Search / Refresh")
        search_layout.addWidget(self.keyword_input)
        search_layout.addWidget(self.search_button)

        mode_group_box = QGroupBox("Compilation Mode")
        mode_layout = QHBoxLayout()
        self.image_mode_radio = QRadioButton("Images")
        self.video_mode_radio = QRadioButton("Videos")
        self.image_mode_radio.setChecked(True)
        self.image_mode_radio.toggled.connect(lambda: self._mode_changed("image"))
        self.video_mode_radio.toggled.connect(lambda: self._mode_changed("video"))
        mode_layout.addWidget(self.image_mode_radio)
        mode_layout.addWidget(self.video_mode_radio)
        mode_layout.addStretch()
        mode_group_box.setLayout(mode_layout)

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

        mode_group_box = QGroupBox("Compilation Mode")
        mode_layout = QHBoxLayout()
        self.image_mode_radio = QRadioButton("Images (Overlay)")
        self.video_mode_radio = QRadioButton("Videos (Full-Screen)")
        self.image_mode_radio.setChecked(True)
        self.image_mode_radio.toggled.connect(lambda: self._mode_changed("image"))
        self.video_mode_radio.toggled.connect(lambda: self._mode_changed("video"))
        mode_layout.addWidget(self.image_mode_radio)
        mode_layout.addWidget(self.video_mode_radio)
        mode_layout.addStretch()
        mode_group_box.setLayout(mode_layout)
        main_layout.addWidget(mode_group_box)
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

    def _mode_changed(self, mode):
        # This function is called when a radio button is toggled.
        # We check which button is checked to set the current mode.
        if self.image_mode_radio.isChecked() and self.current_mode != "image":
            self.current_mode = "image"
            logging.info("Switched to Image Mode.")
            self._clear_grid()
            self._show_placeholder_message("Switched to Image Mode. Enter a keyword to find memes.")
            self.last_keyword_searched = "" # Reset search on mode change
            self.last_post_fullname = None
        elif self.video_mode_radio.isChecked() and self.current_mode != "video":
            self.current_mode = "video"
            logging.info("Switched to Video Mode.")
            self._clear_grid()
            self._show_placeholder_message("Switched to Video Mode. Enter a keyword to find memes.")
            self.last_keyword_searched = "" # Reset search on mode change
            self.last_post_fullname = None

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

        # --- Pagination Logic ---
        # If the keyword is new, it's a new search, so reset pagination.
        # Otherwise, it's a refresh, so we use the 'after' value from the last search.
        if keyword != self.last_keyword_searched:
            logging.info(f"New search detected for keyword '{keyword}'. Resetting pagination.")
            self.last_keyword_searched = keyword
            self.last_post_fullname = None # Reset for new search
            self._clear_grid() # Clear old results for a new search
            self._show_placeholder_message("Searching for new memes...")
        else:
            logging.info(f"Refresh detected for keyword '{keyword}'. Searching after post: {self.last_post_fullname}")
            # If the user clicks refresh but there are no more pages, inform them.
            if not self.last_post_fullname:
                self._handle_error("No more memes found for this keyword. Try a new search.")
                return

        self.search_button.setEnabled(False)
        self.compile_button.setEnabled(False)
        self.status_label.setText(f"Status: Searching for '{keyword}'...")

        # The worker will now be passed the 'after' parameter for pagination.
        # This will be None for a new search, or a post ID for a refresh.
        self.search_worker = RedditSearchWorker(settings, keyword, mode=self.current_mode, after=self.last_post_fullname)
        self.search_worker.finished.connect(self._display_memes)
        self.search_worker.error.connect(self._handle_error)
        self.search_worker.start()

    def _display_memes(self, memes, last_post_fullname):
        self.search_button.setEnabled(True)

        # Store the fullname of the last post for the next refresh.
        # If the worker returns None, it means we've reached the end of the results.
        self.last_post_fullname = last_post_fullname

        # If this was the first search (grid was cleared) and no memes were found.
        if self.meme_grid_layout.count() == 1 and not memes:
             placeholder = self.meme_grid_layout.itemAt(0).widget()
             if isinstance(placeholder, QLabel):
                placeholder.setText("No memes found matching your criteria. Try another keyword.")
                self.status_label.setText("Status: No memes found.")
                return

        # If it was a refresh and no new memes were found.
        if not memes:
            self.status_label.setText("Status: No more memes found for this keyword.")
            return

        # If a placeholder message is present, clear it before adding memes.
        if self.meme_grid_layout.count() == 1:
            placeholder = self.meme_grid_layout.itemAt(0).widget()
            if isinstance(placeholder, QLabel):
                self._clear_grid()

        self.status_label.setText(f"Status: Displaying {len(memes)} new memes. Downloading thumbnails...")
        self.image_downloaders.clear() # Clear old downloaders to manage memory

        # Calculate starting row and col to append new widgets to the grid
        num_existing_items = self.meme_grid_layout.count()
        num_cols = 4
        row = num_existing_items // num_cols
        col = num_existing_items % num_cols

        for meme_data in memes:
            widget = MemeWidget(meme_data)
            self.meme_grid_layout.addWidget(widget, row, col)

            thumbnail_url = meme_data.get('thumbnail_url')
            # Use a placeholder if no thumbnail is available or if it's a reddit placeholder string
            if not thumbnail_url or thumbnail_url in ['self', 'default', 'nsfw']:
                thumbnail_url = "https://www.redditstatic.com/icon.png" # A generic Reddit icon

            downloader = ImageDownloader(thumbnail_url)
            downloader.finished.connect(widget.set_image)
            downloader.error.connect(widget.on_thumbnail_error)
            self.image_downloaders.append(downloader)
            downloader.start()

            col += 1
            if col >= num_cols:
                col = 0
                row += 1

        self.compile_button.setEnabled(True)

    def _extract_frame(self, video_path, output_dir):
        """Extracts the first frame of a video to use as a thumbnail."""
        try:
            with VideoFileClip(video_path) as clip:
                frame_path = os.path.join(output_dir, f"thumb_{uuid.uuid4().hex}.png")
                clip.save_frame(frame_path, t=0)
            return frame_path
        except Exception as e:
            logging.error(f"Failed to extract frame from {video_path}: {e}")
            return None

    def _process_image_for_compilation(self, config, temp_dir):
        """Downloads, transforms, and runs OCR for a single image meme."""
        self.status_label.setText(f"Downloading image: {config['title'][:30]}...")
        QApplication.processEvents()

        response = requests.get(config['url'])
        response.raise_for_status()
        ext = os.path.splitext(config['url'])[1] or '.png'
        image_path = os.path.join(temp_dir, f"img_{uuid.uuid4().hex}{ext}")
        with open(image_path, 'wb') as f: f.write(response.content)
        config['image_path'] = image_path

        transform_dialog = TransformDialog(image_path, self)
        if transform_dialog.exec() != QDialog.DialogCode.Accepted:
            raise InterruptedError("Compilation cancelled.")
        config['transform'] = transform_dialog.get_transform()

        self.status_label.setText(f"Reading text from: {config['title'][:30]}...")
        QApplication.processEvents()
        extracted_text = extract_text_from_image(image_path)

        ocr_dialog = OcrEditDialog(extracted_text, self)
        if ocr_dialog.exec() != QDialog.DialogCode.Accepted:
            raise InterruptedError("Compilation cancelled.")
        config['text'] = ocr_dialog.get_text()

        return config

    def _process_video_for_compilation(self, config, temp_dir):
        """Downloads, gets thumbnail, and transforms a single video meme."""
        self.status_label.setText(f"Downloading video: {config['title'][:30]}...")
        QApplication.processEvents()

        video_path = download_video(config['url'], temp_dir)
        if not video_path:
            logging.warning(f"Skipping video '{config['title']}' due to download failure.")
            return None
        config['video_path'] = video_path

        thumbnail_path = self._extract_frame(video_path, temp_dir)
        if not thumbnail_path:
            logging.warning(f"Skipping video '{config['title']}' due to frame extraction failure.")
            return None

        transform_dialog = TransformDialog(thumbnail_path, self)
        if transform_dialog.exec() != QDialog.DialogCode.Accepted:
            raise InterruptedError("Compilation cancelled.")
        config['transform'] = transform_dialog.get_transform()
        config['text'] = '' # Videos have no TTS

        return config

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
        temp_dir = tempfile.mkdtemp(prefix="meme-compiler-")

        try:
            meme_configs = []
            for i, widget in enumerate(selected_widgets):
                self.status_label.setText(f"Processing item {i+1}/{len(selected_widgets)}...")
                config = widget.meme_data.copy()

                if config.get('type') == 'image':
                    processed_config = self._process_image_for_compilation(config, temp_dir)
                elif config.get('type') == 'video':
                    processed_config = self._process_video_for_compilation(config, temp_dir)
                else:
                    processed_config = None

                if processed_config:
                    meme_configs.append(processed_config)

            if not meme_configs:
                raise ValueError("No valid media items were processed.")

            self.settings = settings
            self.meme_configs_for_compilation = meme_configs
            self.status_label.setText("Fetching available voices...")
            self.fetch_voices_worker = FetchVoicesWorker(api_key=settings.get("elevenlabs_api_key"))
            self.fetch_voices_worker.finished.connect(self._on_voices_fetched)
            self.fetch_voices_worker.error.connect(self._handle_error)
            self.fetch_voices_worker.start()

        except InterruptedError as e:
            self.status_label.setText(str(e))
            shutil.rmtree(temp_dir)
            self._set_ui_enabled(True)
        except Exception as e:
            self._handle_error(f"Failed during pre-compilation setup: {e}")
            if os.path.exists(temp_dir):
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
                    self.current_mode
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
                logging.info(f"Successfully cleaned up temporary directory: {self.temp_dir}")
            except Exception as e:
                logging.error(f"Failed to clean up temporary directory {self.temp_dir}: {e}")

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