import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QTabWidget, QWidget

# Import the tab widgets from their respective files.
# These will be populated with UI elements in the next steps.
from ui_creator_tab import CreatorTab
from ui_settings_tab import SettingsTab

class MainWindow(QMainWindow):
    """
    The main window of the application. It contains the tabbed interface
    for all the application's functionality.
    """
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Meme Video Compiler")
        self.setGeometry(100, 100, 800, 600)  # x, y, width, height

        # Create the tab widget
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # Create and add the tabs
        self.creator_tab = CreatorTab()
        self.settings_tab = SettingsTab()

        self.tabs.addTab(self.creator_tab, "Creator")
        self.tabs.addTab(self.settings_tab, "Settings")


import os

def main():
    """
    The main entry point for the application.
    """
    app = QApplication(sys.argv)

    # Load and apply the stylesheet
    try:
        style_path = os.path.join(os.path.dirname(__file__), "style.qss")
        with open(style_path, "r") as f:
            app.setStyleSheet(f.read())
    except FileNotFoundError:
        print("Stylesheet file 'style.qss' not found. Running with default styles.")

    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
