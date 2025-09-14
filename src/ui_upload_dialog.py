from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QTextEdit,
    QComboBox, QDialogButtonBox
)

class UploadDialog(QDialog):
    """
    A dialog for entering YouTube video details before uploading.
    """
    def __init__(self, upload_count, parent=None):
        super().__init__(parent)
        self.setWindowTitle("YouTube Upload Details")

        # --- UI Widgets ---
        self.title_edit = QLineEdit(f"#{upload_count} #Shorts")
        self.description_edit = QTextEdit()
        self.tags_edit = QLineEdit("memes, funny, reddit, compilation")
        self.privacy_combo = QComboBox()
        self.privacy_combo.addItems(["Private", "Unlisted", "Public"])

        # --- Layout ---
        form_layout = QFormLayout()
        form_layout.addRow("Title:", self.title_edit)
        form_layout.addRow("Description:", self.description_edit)
        form_layout.addRow("Tags (comma-separated):", self.tags_edit)
        form_layout.addRow("Privacy Status:", self.privacy_combo)

        # --- Buttons ---
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setText("Upload")
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        main_layout = QVBoxLayout(self)
        main_layout.addLayout(form_layout)
        main_layout.addWidget(self.button_box)

    def get_upload_details(self) -> dict | None:
        """
        Returns a dictionary with the upload details if the dialog was accepted.
        """
        if self.result() == QDialog.DialogCode.Accepted:
            return {
                "title": self.title_edit.text(),
                "description": self.description_edit.toPlainText(),
                "tags": [tag.strip() for tag in self.tags_edit.text().split(',')],
                "privacy": self.privacy_combo.currentText().lower()
            }
        return None
