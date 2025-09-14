from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QComboBox, QLabel, QDialogButtonBox
)

class VoiceSelectionDialog(QDialog):
    """
    A simple dialog to select a voice from a dropdown menu.
    """
    def __init__(self, voices: list[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select TTS Voice")

        # --- UI Widgets ---
        instruction_label = QLabel("Please select a voice for the compilation:")
        self.voice_combo_box = QComboBox()

        # Populate the combo box with voice names and store the ID as user data
        for voice in voices:
            self.voice_combo_box.addItem(voice.get("name", "Unknown"), userData=voice.get("voice_id"))

        # --- Buttons ---
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        # --- Layout ---
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(instruction_label)
        main_layout.addWidget(self.voice_combo_box)
        main_layout.addWidget(self.button_box)

    def get_selected_voice_id(self) -> str | None:
        """
        Returns the voice_id of the selected voice if the dialog was accepted.
        """
        if self.result() == QDialog.DialogCode.Accepted:
            return self.voice_combo_box.currentData()
        return None
