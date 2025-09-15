import sys
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QTextEdit, QDialogButtonBox, QLabel
)
from PyQt6.QtCore import Qt

class OcrEditDialog(QDialog):
    """
    A dialog box that allows the user to review and edit text
    that has been extracted via OCR from a meme image.
    """
    def __init__(self, original_text, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Meme Text")
        self.setMinimumSize(400, 300)

        self.layout = QVBoxLayout(self)

        instruction_label = QLabel("Review and edit the text extracted from the meme:", self)
        self.layout.addWidget(instruction_label)

        self.text_edit = QTextEdit(self)
        self.text_edit.setPlainText(original_text)
        self.layout.addWidget(self.text_edit)

        # Standard buttons (OK & Cancel)
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.layout.addWidget(self.button_box)

    def get_text(self):
        """Returns the (potentially edited) text from the text box."""
        return self.text_edit.toPlainText().strip()
