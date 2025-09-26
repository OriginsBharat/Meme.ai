# Meme Video Compiler

This is a desktop application designed to automatically fetch memes from Reddit, generate text-to-speech audio for them, and compile them into a video, ready for sharing or uploading to YouTube.

## Features

- **Keyword-based Meme Fetching:** Searches Reddit for image-based memes based on your keywords.
- **Smart Filtering:** Filters memes by upvote count (500+) and for posts with at least two comments containing the word "relatable".
- **OCR and TTS:** Automatically extracts text from image memes using Tesseract OCR and generates voiceovers using the ElevenLabs API.
- **Automated Video Compilation:** Combines an intro, the selected memes, a background video, background music, and an outro into a single video file.
- **YouTube Integration:** Option to upload the final video directly to your YouTube channel.
- **Customizable UI:** A dark theme with neon pink and purple highlights.
- **Standalone Executable:** A build script is provided to package the application into a single `.exe` file.

## Setup and Configuration

### Prerequisites
1.  **Python:** Ensure you have Python 3.10 or newer installed. You can download it from [python.org](https://www.python.org/).
2.  **Tesseract OCR:** This application requires the Tesseract OCR engine, which must be installed separately.
    -   Download and install it from the official Tesseract repository: [https://github.com/tesseract-ocr/tesseract](https://github.com/tesseract-ocr/tesseract)
    -   During installation, note the full path to the `tesseract.exe` file (e.g., `C:\Program Files\Tesseract-OCR\tesseract.exe`). You will need this for the app's settings.

### Installation
1.  **Clone the repository:**
    ```bash
    git clone <repository_url>
    cd <repository_directory>
    ```
2.  **Install Python dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

### Configuration
Before you can use the app, you must configure your API keys and file paths in the **Settings** tab:

1.  **Reddit API Credentials:**
    -   Go to [Reddit's app preferences](https://www.reddit.com/prefs/apps).
    -   Create a new "script" app.
    -   Enter the `client ID` and `client secret` into the settings.
    -   For `User Agent`, you can enter something descriptive, like `MemeCompilerApp/1.0 by YourUsername`.
2.  **ElevenLabs API Key:**
    -   Sign up at [ElevenLabs](https://elevenlabs.io/).
    -   Find your API key in your profile settings and enter it.
3.  **Google Client Secrets File (for YouTube Upload):**
    -   Go to the [Google Cloud Console](https://console.cloud.google.com/).
    -   Create a new project.
    -   Enable the "YouTube Data API v3".
    -   Create credentials for an "OAuth 2.0 Client ID" of type "Desktop application".
    -   Download the `client_secrets.json` file.
    -   In the app's settings, browse to and select this downloaded JSON file.
4.  **Tesseract Configuration:**
    -   **Tesseract Executable:** Enter the full path to `tesseract.exe` that you noted during installation.
    -   **Tessdata Directory:** You must also provide the path to the `tessdata` directory. This folder is located in your Tesseract installation directory (e.g., `C:\Program Files\Tesseract-OCR\tessdata`). Both paths are required for OCR to function correctly.
5.  **Media Files:**
    -   Use the "Browse..." buttons to select your default intro, outro, background video, and background music files.

**Click "Save Settings" after entering all your information.**

## How to Use

### Running from Source
To run the application directly without building the executable:
```bash
python src/main.py
```

### Building the Executable (`.exe`)
To create a single, standalone `.exe` file that you can run on any Windows machine (without needing Python installed there):
1.  Make sure you have installed all dependencies from `requirements.txt`.
2.  Run the build script:
    ```bash
    python build.py
    ```
3.  The build process may take a few minutes. Once it's complete, you will find `MemeVideoCompiler.exe` inside the `dist` folder.