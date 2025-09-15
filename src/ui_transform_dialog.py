from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGraphicsView, QGraphicsScene,
    QGraphicsPixmapItem, QSlider, QPushButton, QLabel, QGraphicsRectItem
)
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QPixmap, QColor, QPen

class TransformDialog(QDialog):
    """
    An interactive dialog to let the user position and scale a meme image.
    """
    def __init__(self, image_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Position and Scale Meme")

        # --- Data ---
        self.image_pixmap = QPixmap(image_path)
        if self.image_pixmap.isNull():
            # Handle case where image fails to load
            self.image_pixmap = QPixmap(100, 100)
            self.image_pixmap.fill(QColor("red"))

        # --- UI Widgets ---
        self.scene = QGraphicsScene()
        self.scene.setBackgroundBrush(QColor("black"))
        self.scene.setSceneRect(0, 0, 1080, 1920)

        # Add the dotted reference outline
        outline = QGraphicsRectItem(self.scene.sceneRect())
        pen = QPen(Qt.GlobalColor.white)
        pen.setStyle(Qt.PenStyle.DashLine)
        outline.setPen(pen)
        self.scene.addItem(outline)

        self.view = QGraphicsView(self.scene)

        self.image_item = QGraphicsPixmapItem(self.image_pixmap)
        self.image_item.setFlag(QGraphicsPixmapItem.GraphicsItemFlag.ItemIsMovable)
        self.scene.addItem(self.image_item)

        # Center the item initially
        item_rect = self.image_item.boundingRect()
        self.image_item.setPos(
            (self.scene.width() - item_rect.width()) / 2,
            (self.scene.height() - item_rect.height()) / 2
        )

        self.scale_slider = QSlider(Qt.Orientation.Horizontal)
        self.scale_slider.setRange(10, 200) # 10% to 200%
        self.scale_slider.setValue(100)
        self.scale_slider.valueChanged.connect(self._set_scale)

        self.next_button = QPushButton("Next Meme")
        self.cancel_button = QPushButton("Cancel")
        self.next_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)

        # --- Layout ---
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.view)

        slider_layout = QHBoxLayout()
        slider_layout.addWidget(QLabel("Scale:"))
        slider_layout.addWidget(self.scale_slider)
        main_layout.addLayout(slider_layout)

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.next_button)
        main_layout.addLayout(button_layout)

        self.resize(560, 1000) # Set a reasonable default size

    def showEvent(self, event):
        """Fit the scene in the view when the dialog is first shown."""
        super().showEvent(event)
        self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event):
        """Fit the scene in the view whenever the dialog is resized."""
        super().resizeEvent(event)
        self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def _set_scale(self, value):
        """Applies scale to the graphics item."""
        scale_factor = value / 100.0
        self.image_item.setScale(scale_factor)

    def get_transform(self) -> dict | None:
        """
        Returns the final transform data if the dialog was accepted.
        """
        if self.result() == QDialog.DialogCode.Accepted:
            pos = self.image_item.pos()
            return {
                "scale": self.image_item.scale(),
                "pos": (pos.x(), pos.y())
            }
        return None
