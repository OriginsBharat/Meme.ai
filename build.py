import subprocess
import os
import sys

def main():
    """
    This script runs PyInstaller to build the executable for the application.
    """
    # The name of your main Python script
    script_name = os.path.join("src", "main.py")

    # The name for the final executable
    exe_name = "MemeVideoCompiler"

    # Path to the icon file
    icon_path = "icon.ico"

    # Path to the stylesheet data
    # The format is 'source:destination'
    # We add style.qss to the root of the bundle
    stylesheet_path = os.path.join("src", "style.qss")
    data_to_add = f"{stylesheet_path}{os.pathsep}."

    # PyInstaller command
    command = [
        "pyinstaller",
        "--name", exe_name,
        "--onefile",
        "--windowed", # Use '--console' for debugging
        f"--icon={icon_path}",
        f"--add-data={data_to_add}",
        script_name
    ]

    print("Running PyInstaller with the following command:")
    print(" ".join(command))

    try:
        subprocess.run(command, check=True, shell=(sys.platform == 'win32'))
        print("\nBuild successful!")
        print(f"You can find the executable in the '{os.path.join(os.getcwd(), 'dist')}' directory.")
    except FileNotFoundError:
        print("\nError: 'pyinstaller' command not found.")
        print("Please make sure you have installed PyInstaller by running:")
        print("pip install pyinstaller")
    except subprocess.CalledProcessError as e:
        print(f"\nAn error occurred during the build process: {e}")

if __name__ == "__main__":
    main()
