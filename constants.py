import sys
import os
import appdirs
from enum import Enum

WINDOW_ICON_PATH_SUFFIX = os.path.join("resources", "icon.ico")
STYLE_PATH_SUFFIX = os.path.join("resources", "style.qss")
IMAGE_PATH_SUFFIX = os.path.join("resources", "icon.png")
FONTS_PATH_SUFFIX = os.path.join("resources", "fonts")

APPLICATION_DIRECTORY = appdirs.user_data_dir("EZDeadlockModManager", "")
SETTINGS_FILE_PATH = os.path.join(APPLICATION_DIRECTORY, "settings.json")
DOWNLOAD_FOLDER = os.path.join(APPLICATION_DIRECTORY, "Downloads")
TEMPORARY_FOLDER_PREFIX = "EZDeadlockDownload_"

RESPONSE_WAIT_TIME = 5
JSON_INDENT_AMOUNT = 2

def get_resource_path(relative_path: str) -> str:
    '''
    Returns the temporary location of a bundled data path, or the actual location (if run in development/python).
    See https://pyinstaller.org/en/stable/runtime-information.html#using-pyinstaller-runtime-information
    '''
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class Paginate(Enum):
    '''
    An enumeration used for the Mod Browser's search function, to determine whether the catalogue should change pages.
    '''
    DO_NOT_PAGINATE = 0
    PREVIOUS_PAGE = 1
    NEXT_PAGE = 2