from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QPushButton, QListWidget, QFileDialog,
                              QListWidgetItem, QLineEdit, QLabel, QHBoxLayout, QCheckBox, QMessageBox)
from PyQt5.QtGui import (QIcon, QPixmap, QFontDatabase, QDropEvent, QDragMoveEvent, QCloseEvent)
from PyQt5.QtCore import Qt

import py7zr
import rarfile
import zipfile
import sys
import shutil
import os
import threading
import re
import filecmp
import errno
import json

try:
    import winreg
    WINREG_IMPORTED = True
except ImportError: #this is thrown when executed on any os that isn't windows
    WINREG_IMPORTED = False

from constants import *
import deadlock_mod_browser

APPLICATION_TITLE = "EZ Deadlock Mod Manager"
APPLICATION_DIMENSIONS = [100, 100, 1000, 800]
WARNING_DIMENSION = 20

#extracted mods are stored in the paths here
GAMEBANANA_DIRECTORY = os.path.join(APPLICATION_DIRECTORY, "GameBanana")
MOD_DIRECTORY = os.path.join(GAMEBANANA_DIRECTORY, "Mods")
SOUND_DIRECTORY = os.path.join(GAMEBANANA_DIRECTORY, "Sounds")
VPK_DIRECTORY = os.path.join(APPLICATION_DIRECTORY, "VPK Files")

#these are always found under /Deadlock/
DEADLOCK_ADDON_SUBDIRECTORY = os.path.join("game", "citadel", "addons")
DEADLOCK_GAME_SUBDIRECTORY = os.path.join("game", "bin", "win64", "deadlock.exe")

#these are just to make things easier for most users on windows when autoconfiguring the game's path
DEFAULT_GAME_FOLDER = os.path.join("C:\\", "Program Files (x86)", "Steam", "steamapps", "common", "Deadlock")
DEFAULT_ADDON_DIRECTORY = os.path.join("C:\\", "Program Files (x86)", "Steam", "steamapps", "common", "Deadlock", "game", "citadel", "addons")
DEFAULT_GAME_EXECUTABLE_PATH = os.path.join("C:\\", "Program Files (x86)", "Steam", "steamapps", "common", "Deadlock", "game", "bin", "win64", "deadlock.exe")

#the maximum .vpk files that are loadable within the game, we will never copy over more than this amount into the game's addon folder
MAXIMUM_MOD_AMOUNT = 99

#these are for detecting installed .rar file tools on windows
RAR_TOOL_REGISTRY_PATHS = {
    "winrar": [
        r"SOFTWARE\\Microsoft\Windows\\CurrentVersion\App Paths\\winrar.exe",
        r"SOFTWARE\WOW6432Node\\Microsoft\Windows\\CurrentVersion\App Paths\\winrar.exe"]
}
RAR_TOOL_EXECUTABLES = {
    "winrar": "UnRAR.exe"
}

def check_game_folder(path: str) -> bool:
    '''
    Checks the given game path for the game's addon folder (to load the mods) and executable folder (to start the game).
    This should pretty much always be the 'Deadlock' folder under /steamapps/common/.
    Returns True if the game folder contains both paths, returns False otherwise.
    '''
    return os.path.exists(os.path.join(path, DEADLOCK_ADDON_SUBDIRECTORY)) and os.path.exists(os.path.join(path, DEADLOCK_GAME_SUBDIRECTORY))

def delete_path_and_parent_recursive(path: str) -> None:
    '''
    If path is a file, removes the file and calls delete_folder_parent_recursive on the parent directory.
    If path is a folder, removes it if empty and calls delete_folder_parent_recursive on the parent, or if it is populated then return.
    Returns if the path given is the application's base directory, or if there is an error removing the file/folder at the path.
    Used for deleting mods that have many subfolders due to extracting from archives.
    '''
    if path == APPLICATION_DIRECTORY:
        return
    if not os.path.exists(path):
        return
    parent = os.path.dirname(path)
    if os.path.isdir(path):
        try:
            if not os.listdir(path):
                os.rmdir(path)
                delete_path_and_parent_recursive(parent)
        except:
            return
    else:
        try:
            os.remove(path)
            delete_path_and_parent_recursive(parent)   
        except:
            return
        
def find_rar_tool() -> tuple[str | None, str | None]:
    '''
    Attempts to find the location of an available .rar tool executable, in order to extract .vpk files from any possible downloaded .rar archives.
    On windows, queries the registry for typical installation paths of popular .rar tools, see RAR_TOOL_REGISTRY_PATHS.
    Returns a tuple containing the name of the tool and its file path as strings, or (None, None) if no tool was discovered.
    '''
    if WINREG_IMPORTED:
        for name, path_list in RAR_TOOL_REGISTRY_PATHS.items():
            for path in path_list:
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as key:
                        tool_path, _ = winreg.QueryValueEx(key, "")
                        return name, tool_path
                except FileNotFoundError:
                    continue
    return None, None

class ModManager(QWidget):
    '''
    The main mod manager application.
    '''
    def __init__(self) -> None:
        super().__init__()

        path_to_icon = get_resource_path(WINDOW_ICON_PATH_SUFFIX)
        self.setWindowIcon(QIcon(path_to_icon))
        self.setWindowTitle(APPLICATION_TITLE)
        self.setGeometry(*APPLICATION_DIMENSIONS)
        self.setObjectName("modmanager")

        #these references belong to the mod browser (not mod list) and are needed to ensure that they aren't garbage collected
        self.workers_and_threads = {}
        self.worker_thread_lock = threading.Lock()
        self.mod_browser = None

        self.settings_menu = None

        self.finished_initial_load = False #set once .read_profile() is called successfully and mod list is loaded
        self.rar_tool_found = False

        #these are set once .load_settings() is called successfully
        self.game_files_found = False
        self.current_game_folder = ""
        self.current_addon_directory = ""
        self.current_game_executable_path = ""

        self.layout = QVBoxLayout()

        #main title and image
        title_label = QLabel(APPLICATION_TITLE)
        title_label.setObjectName("title")
        self.layout.addWidget(title_label)
        title_label.setAlignment(Qt.AlignCenter)
        
        image_label = QLabel(self)
        path_to_image = get_resource_path(IMAGE_PATH_SUFFIX)
        pixmap = QPixmap(path_to_image)
        scaled_pixmap = pixmap.scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        image_label.setPixmap(scaled_pixmap)
        image_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(image_label)

        #layout with both buttons to add mods
        top_button_layout = QHBoxLayout()

        self.gamebanana_button = QPushButton("Browse Mods on 🍌GameBanana")
        self.gamebanana_button.clicked.connect(self.open_mod_browser)
        top_button_layout.addWidget(self.gamebanana_button)

        self.add_button = QPushButton("Add Mods Manually (.vpk or archive files)")
        self.add_button.clicked.connect(self.add_mods_manually)
        top_button_layout.addWidget(self.add_button)

        self.layout.addLayout(top_button_layout)

        #search bar for installed mods
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search your installed mods here!")
        self.search_bar.returnPressed.connect(self.search_mods)
        self.search_bar.textChanged.connect(self.reset_search_index)
        self.layout.addWidget(self.search_bar)
        #these are for self.search_mods() functionality
        self.search_index = 0
        self.search_term = ""

        #the custom mod list widget
        self.list_label = QLabel("Drag and drop to change load order! You can also toggle mods on and off!")
        self.layout.addWidget(self.list_label)
        self.list_widget = NumberedModListWidget(self)
        self.layout.addWidget(self.list_widget)

        #the rest of the buttons
        self.load_button = QPushButton("Load Mod Configuration to Game Folder")
        self.load_button.clicked.connect(self.save_mods)
        self.layout.addWidget(self.load_button)

        self.launch_button = QPushButton("Launch Game (requires Steam running)")
        self.launch_button.clicked.connect(self.start_game)
        self.layout.addWidget(self.launch_button)

        self.open_settings_button = QPushButton("Settings ⚙️")
        self.open_settings_button.clicked.connect(self.open_settings_menu)
        self.layout.addWidget(self.open_settings_button)

        #game file warning (changes based on self.game_files_found)
        self.file_warning_widget = QWidget()
        file_warning_layout = QHBoxLayout()
        self.file_warning = QLabel()
        self.file_warning.setObjectName("file-warning-bad")
        self.file_warning.setFixedSize(WARNING_DIMENSION, WARNING_DIMENSION)
        file_warning_layout.addWidget(self.file_warning)

        self.file_warning_label = QLabel()
        file_warning_layout.addWidget(self.file_warning_label)
        self.file_warning_widget.setLayout(file_warning_layout)

        self.layout.addWidget(self.file_warning_widget)
        self.set_file_warning(False)

        #download warning (only becomes visible when downloading)
        self.download_warning_widget = QWidget()

        download_warning_layout = QHBoxLayout()
        download_warning = QLabel()
        download_warning.setFixedSize(WARNING_DIMENSION, WARNING_DIMENSION)
        download_warning.setObjectName("download-warning")
        download_warning_layout.addWidget(download_warning)

        download_warning_label = QLabel()
        download_warning_label.setText("Mods are currently being downloaded!")
        download_warning_layout.addWidget(download_warning_label)
        self.download_warning_widget.setLayout(download_warning_layout)

        self.layout.addWidget(self.download_warning_widget)
        self.download_warning_widget.setVisible(False)

        self.setLayout(self.layout)

        #the gui is now done, load the game's folder path from the settings file
        if not self.load_settings():
            QMessageBox.information(self, "Warning!", f"There was an error loading the settings. Please ensure that this application has sufficient permissions, " \
                f"and that the application folder at: {APPLICATION_DIRECTORY} has sufficient read/write permissions.")

        if not self.rar_tool_found:
            rar_tool_name, rar_tool_path = find_rar_tool()
            if rar_tool_name and os.path.exists(os.path.join(os.path.dirname(rar_tool_path), RAR_TOOL_EXECUTABLES[rar_tool_name])):
                rarfile.UNRAR_TOOL = os.path.join(os.path.dirname(rar_tool_path), RAR_TOOL_EXECUTABLES[rar_tool_name])
                self.rar_tool_found = True
            else:
                QMessageBox.information(self, "Warning!", "No .rar extractor found! .rar files will not be extracted, and mods within them cannot be used." \
                " Other file formats (.zip, .7z, and .vpk) are operational. If you wish to use mods within .rar files, a known working tool is WinRAR (it is free):\n" \
                "https://www.win-rar.com/")

        self.read_profile() #this will populate the mod list from entries in the settings
        self.finished_initial_load = True

    def set_file_warning(self, files_detected: bool) -> None:
        '''
        Toggles the colour and text of the file warning at the bottom of the mod manager according to the value of files_detected.
        Call this appropriately when the game folder changes location and when game files are found.
        '''
        if files_detected:
            self.file_warning.setObjectName("file-warning-good")
            self.file_warning.style().polish(self.file_warning)
            self.file_warning_label.setText("Game files detected!")
        else:
            self.file_warning.setObjectName("file-warning-bad")
            self.file_warning.style().polish(self.file_warning)
            self.file_warning_label.setText("Game files not detected! Try clicking the 'change game folder' button!")

    def load_settings(self) -> bool:
        '''
        Loads the application's settings from SETTINGS_FILE_PATH. This currently includes the game folder location, rar tool location, and the mod list.
        Returns True if the settings folder was loaded successfully, False if not.
        '''
        try:
            if os.path.exists(SETTINGS_FILE_PATH):
                with open(SETTINGS_FILE_PATH, "r", encoding="utf-8") as settings_file:
                    settings = json.load(settings_file)
                    if "game_folder_location" in settings:
                        if check_game_folder(settings["game_folder_location"]):
                            self.found_game_files(settings["game_folder_location"])
                        else:
                            QMessageBox.information(self, "Attention!", "If you are seeing this message, "\
                                "the mod manager could not find your game folder. Please select it with the button at the bottom.")
                            
                    if "rar_tool_location" in settings and settings["rar_tool_location"]:
                        self.rar_tool_found = True
                        rarfile.UNRAR_TOOL = settings["rar_tool_location"]

            else: #create a blank settings file
                settings = {}
                settings["game_folder_location"] = ""
                settings["rar_tool_location"] = ""
                settings["mods"] = []
                with open(SETTINGS_FILE_PATH, "w", encoding="utf-8") as settings_file:
                    json.dump(settings, settings_file, indent=JSON_INDENT_AMOUNT)
            return True
        except:
            return False

    def found_game_files(self, game_folder_path) -> None:
        '''
        Call this when game files are detected. 
        Updates the current file paths and games_file_found to be accurate, and updates the message at the bottom of the client.
        '''
        self.game_files_found = True
        self.current_game_folder = game_folder_path
        self.current_addon_directory = os.path.join(game_folder_path, DEADLOCK_ADDON_SUBDIRECTORY)
        self.current_game_executable_path = os.path.join(game_folder_path, DEADLOCK_GAME_SUBDIRECTORY)
        
        #set the message at the bottom to indicate the new status
        self.set_file_warning(True)

    def add_mods_manually(self) -> None:
        '''
        Opens a file dialog to add one or multiple .vpk files, or archive files that contain .vpk file(s) to the mod list.
        '''
        files, _ = QFileDialog.getOpenFileNames(self, "Select Files", filter=self.tr(".vpk or archive files (*.vpk *.zip *.7z *.rar)"))
        self.add_mod(files)

    def _add_mods_helper(self, archive_file_name: str, vpk_name: str, from_gamebanana: bool, mod_real_name: str="", gamebanana_item_type: str="", gamebanana_mod_number: int=0,
        source_file: None | zipfile.ZipExtFile | py7zr.SevenZipFile | rarfile.RarFile = None) -> None:
        '''
        Helper for add_mods(). Writes the mod to a folder that corresponds to both its item type and mod number from gamebanana, and adds it to the mod list within the
        mod manager. Manually added mods check the VPK_DIRECTORY for any duplicates, and are not added if a duplicate is found.
        '''
        match gamebanana_item_type:
            case "Mod":
                mod_path = os.path.join(MOD_DIRECTORY, str(gamebanana_mod_number))
                file_path = os.path.join(mod_path, os.path.splitext(os.path.basename(archive_file_name))[0])
            case "Sound":
                mod_path = os.path.join(SOUND_DIRECTORY, str(gamebanana_mod_number))
                file_path = os.path.join(mod_path, os.path.splitext(os.path.basename(archive_file_name))[0])
            case _: #manually added mods get added to a different path
                #this doesnt matter
                mod_path = VPK_DIRECTORY
                file_path = os.path.join(mod_path, "Unnamed_VPK_0.vpk")

        os.makedirs(mod_path, exist_ok=True) #e.x. /APPLICATION DIRECTORY/Mods/game_banana_mod_number/

        #alert the user that we are overwriting an older version of a mod
        mod_already_present = False
        if gamebanana_item_type == "Mod" or gamebanana_item_type == "Sound":
            if os.path.exists(os.path.join(file_path, vpk_name)):
                mod_already_present = True
                QMessageBox.information(self, "Alert!", "Mod already exists! Overwriting...")
                #TODO: remove the previous contents of the file path

        #must ensure a unique name for any manually added mods (they receive an anonymous name because they are not officially part of the gamebanana library)
        if not gamebanana_item_type:
            vpk_index = 0
            while (os.path.exists(os.path.join(VPK_DIRECTORY, "Unnamed_VPK_" + str(vpk_index))) or os.path.exists(os.path.join(VPK_DIRECTORY, "Unnamed_VPK_" + str(vpk_index) + ".vpk"))):
                vpk_index += 1
            file_path = os.path.join(VPK_DIRECTORY, "Unnamed_VPK_" + str(vpk_index))
            
        #write the mod to the destination
        match type(source_file):
            case zipfile.ZipExtFile:
                os.makedirs(os.path.join(file_path, os.path.dirname(vpk_name)), exist_ok=True)
                with open(os.path.join(file_path, vpk_name), 'wb') as target_file:
                    target_file.write(source_file.read())
            case py7zr.SevenZipFile:
                source_file.extract(targets=[vpk_name], path=file_path)
            case rarfile.RarFile:
                source_file.extract(vpk_name, path=file_path)
            case _:
                if not gamebanana_item_type:
                    file_path += ".vpk"
                shutil.copy(archive_file_name, file_path)
                archive_file_name = ""
        
        mod_file_path = file_path
        if archive_file_name:
            mod_file_path = os.path.join(file_path, vpk_name) 
            if WINREG_IMPORTED: #for some reason subfolders in archive folders always have forward slashes instead of backslashes on windows, this is mostly harmless though
                mod_file_path = mod_file_path.replace("/", "\\")

        #duplicate protection for manually added mods
        if not gamebanana_item_type:

            def recursively_find_vpk(vpk_list: str) -> bool:
                '''
                Tries to find a previously added vpk file that exactly matches the one we are trying to add. Checks all files within vpk_list, and 
                recursively searches folders within vpk_list. If it finds a match, loops through the mod list to find
                that exact entry, and notifies the user of its existence before deleting the new file (not the old one) and returning True. Returns False otherwise.
                '''
                for vpk_file in vpk_list:
                    if os.path.isdir(vpk_file):
                        if recursively_find_vpk([os.path.abspath(os.path.join(vpk_file, vpk)) for vpk in os.listdir(vpk_file)]) is True:
                            return True
                    
                    elif vpk_file != mod_file_path and filecmp.cmp(mod_file_path, vpk_file, shallow=False): #same exact vpk already exists
                        print("Found match at " + vpk_file)
                        for i in range(self.list_widget.count()): #loop through the mod list to inform the user of the duplicate mod
                            item = self.list_widget.item(i)
                            item_widget = self.list_widget.itemWidget(item)
                            if item_widget.file_path == vpk_file:
                                QMessageBox.information(self, "Alert!", "Mod already added: " + item_widget.label.text() + ". Its path is at: " + vpk_file)
                                try:
                                    delete_path_and_parent_recursive(mod_file_path)
                                    return True
                                except Exception as e:
                                    print("Error, could not remove duplicate .vpk file: " + str(e))
                                    return False
                        #if we got here then there is likely a problem with the mod list (or how it was loaded) or the user deleted a file manually, as this should not naturally occur
                        return False
                return False
            
            vpk_file_list = [os.path.abspath(os.path.join(VPK_DIRECTORY, vpk_file)) for vpk_file in os.listdir(VPK_DIRECTORY)]
            mod_already_present = recursively_find_vpk(vpk_file_list)

        if not mod_already_present: #add the mod to the mod list since its not there
            #the name is a combination of the real_name given and the filename, this is because of multiple file versions
            mod_name = mod_real_name + " (" + os.path.join(os.path.basename(archive_file_name), vpk_name) + ")"
            item_widget = ModListItem(mod_name, mod_file_path, self.list_widget, main_window=self, number=self.list_widget.count() + 1, from_gamebanana=from_gamebanana)
            list_item = QListWidgetItem(self.list_widget)
            item_widget.add_to_list(list_item)
            self.list_widget.scrollToItem(self.list_widget.item(self.list_widget.count() - 1), hint=QListWidget.PositionAtTop)

        return True

    def add_mod(self, files: list[str], real_name: str="", item_type: str="", number: int=0) -> None:
        '''
        Takes a list of file paths to mods and adds them to the mod list. Valid file types are .vpk, .zip, .7z, and .rar.
        If mods are added manually: real_name, item_type, and number should not be set, as these as reserved for mods downloaded from gamebanana.
        '''
        if (item_type and not number) or (number and not item_type): #this is an invalid combination
            return False
        
        if real_name and item_type:
            from_gamebanana = True
        else:
            from_gamebanana = False

        #remove the non-filename characters from the real name just in case
        real_name = re.sub(r'[<>:"/\\|?*]', '', real_name)
        real_name = real_name.strip().strip('.')

        for file in files:
            try:
                _, file_extension = os.path.splitext(file)
                match file_extension:
                    case ".zip":
                        with zipfile.ZipFile(file, 'r') as zip_file:
                            for name in zip_file.namelist():
                                if ".vpk" in name:
                                    with zip_file.open(name) as source_file:
                                        self._add_mods_helper(file, name, from_gamebanana, real_name, item_type, number,
                                                                source_file=source_file)
                    case ".vpk":
                        self._add_mods_helper(file, file, from_gamebanana, real_name, item_type, number) #the archive name is just the filename
                    case ".7z":
                        with py7zr.SevenZipFile(file, mode='r') as archive:
                            file_list = archive.getnames()
                            for name in file_list:
                                _, extracted_file_extension = os.path.splitext(name)
                                if extracted_file_extension == ".vpk":
                                    self._add_mods_helper(file, name, from_gamebanana, real_name, item_type, number,
                                                            source_file=archive)
                    case ".rar":
                        #warning: needs external .rar tool, also copies folders too like .7z archive extraction
                        with rarfile.RarFile(file) as archive:
                            for info in archive.infolist():
                                _, extracted_file_extension = os.path.splitext(info.filename)
                                if extracted_file_extension == ".vpk":
                                    self._add_mods_helper(file, info.filename, from_gamebanana, real_name, item_type, number,
                                                            source_file=archive)
                    case _:
                        return
            except Exception as e:
                print(e)
                QMessageBox.information(self, "Error", "Error with adding mods. Check if the file(s) are of a valid format, and if it is a .rar file, check if you have a valid unrar tool.")
                return
        self.save_profile() #this makes it so that we save the new file path as an added mod to our configuration
    
    def _search_mods_helper(self, mod_list_index: int) -> bool:
        '''
        Helper for self.search_mods. Scrolls to and selects whatever mod is found, and increments self.search_index (modulo the length of the mod list).
        Returns True if it finds the next mod that matches the text in self.search_term, returns False otherwise.
        '''
        item_widget = self.list_widget.itemWidget(self.list_widget.item(mod_list_index))
        if self.search_term.lower() in item_widget.name.lower():
            self.list_widget.scrollToItem(self.list_widget.item(mod_list_index), hint=QListWidget.PositionAtTop)
            self.search_index = (mod_list_index + 1) % self.list_widget.count()
            self.list_widget.setCurrentItem(self.list_widget.item(mod_list_index))
            self.list_widget.item(mod_list_index).setSelected(True)
            return True
        return False

    def search_mods(self) -> bool:
        '''
        Scrolls to and selects the next mod in the list (according to self.search_index) that contains the text in self.search_term (case-insensitive). Wraps around.
        Return True if at least one mod in the mod list matches. Return False otherwise. self.search_term is updated every time the user presses Enter in the search bar.
        If a mod is found, sets self.search_index to the next index after that mod, so that the next call to search_mods won't bring up this mod again (unless only this mod matches).
        Sets the self.search_index back to 0 if no mod is found.
        '''
        if self.search_index >= self.list_widget.count():
            self.search_index = 0

        for mod_list_index in range(self.search_index, self.list_widget.count()):
            if self._search_mods_helper(mod_list_index):
                return True
        for mod_list_index in range(0, self.list_widget.count()): #loop back around to the top of the mod list
            if self._search_mods_helper(mod_list_index):
                return True
        self.search_index = 0
        return False

    def reset_search_index(self) -> None:
        '''
        Resets the search index and changes self.search_term to the search bar's text. Only to be called when the search bar text is altered.
        This is to enable the user to search through every mod in the list (according to their query) using the Enter key, 
        and only change their query when the actual text in the search bar changes.
        '''
        self.search_index = 0
        self.search_term = self.search_bar.text()

    def save_profile(self) -> bool:
        '''
        Saves the mod list information to SETTINGS_FILE_PATH. Overwrites any preexisting mod data in the settings file.
        Returns True if the mod data was saved successfully, False if not. Call this function after adding, deleting, renaming, toggling or change the load order of mods.
        '''
        try:
            settings = {}
            with open(SETTINGS_FILE_PATH, "r", encoding="utf-8") as settings_file:
                settings = json.load(settings_file)

            settings["mods"] = []
            for i in range(self.list_widget.count()):
                mod = {}
                item_widget = self.list_widget.itemWidget(self.list_widget.item(i))
                mod["name"] = item_widget.name
                mod["file_path"] = item_widget.file_path
                if item_widget.toggle.isChecked():
                    mod["toggled_on"] = True
                else:
                    mod["toggled_on"] = False
                mod["from_gamebanana"] = item_widget.from_gamebanana
                settings["mods"].append(mod)

            with open(SETTINGS_FILE_PATH, "w", encoding="utf-8") as settings_file:
                json.dump(settings, settings_file, indent=JSON_INDENT_AMOUNT)
            return True
        except:
            return False

    def read_profile(self) -> bool:
        '''
        Reads the mod list information from SETTINGS_FILE_PATH, and loads it into the mod list.
        Removes all items from the mod list gui.
        Returns True if the mod data was read successfully, False if not.
        '''
        while (self.list_widget.count() > 0): #erase the current mod list
            self.list_widget.takeItem(0)

        try:
            settings = {}
            with open(SETTINGS_FILE_PATH, "r", encoding="utf-8") as settings_file:
                settings = json.load(settings_file)

            vpk_index = 1
            for mod in settings["mods"]:
                file_path = mod["file_path"]
                real_name = mod["name"]
                from_gamebanana = mod["from_gamebanana"]

                item_widget = ModListItem(real_name, file_path, self.list_widget, main_window=self, number=vpk_index, from_gamebanana=from_gamebanana)
                list_item = QListWidgetItem(self.list_widget)

                if mod["toggled_on"]:
                    item_widget.toggle.setChecked(True)
                else:
                    item_widget.toggle.setChecked(False)

                item_widget.add_to_list(list_item)
                vpk_index += 1
            return True
        except:
            return False

    def save_mods(self) -> bool:
        '''
        Returns True if all enabled mods (with valid file paths) and the gameinfo.gi file were successfully saved to the current_addon_directory without error, False if not.
        Rewrites the gameinfo.gi file to contain the lines necessary to detect mods in game.
        Then saves the enabled mods in the mod list (as symbolic links) to the game's addon folder, if detected.

        Writes the mods in order with the filename format 'pakXX_dir.vpk' where XX is a number for 01-99 zero padded.
        Starts from 1 and counts upward with each mod that is currently checked, does not add mods that are not checked. 
        This means that numbers on the modlist and numbers in the addon folder will differ if some mods are disabled.
        Deletes mods that have invalid file paths, and removes them from the mod list. Stops saving mods to the addon folder after MAXIMUM_MOD_AMOUNT is reached.

        Additionally, we load the mods based on the mod list data, not the settings.json data, though these should be synced.
        '''
        if not self.game_files_found:
            QMessageBox.information(self, "Attention!", "If you are seeing this message, the mod manager can't load your mods because it could not find your game folder." \
            " Please select it with the button at the bottom.")
            return False
        try:
            #first we modify the gameinfo.gi file (just replaces it with the modified version with +3 lines to support modding)
            game_info_file_path = os.path.join(self.current_game_folder, "game", "citadel", "gameinfo.gi")
            with open(game_info_file_path, "r") as f:
                lines = f.readlines()
            target = "Game_Languagecitadel_*LANGUAGE*" #the edited lines must come after this one
            edited_lines = {"\t\t\tMod\t\t\t\t\tcitadel\n": False, "\t\t\tWrite\t\t\t\tcitadel\n": False, "\t\t\tGame\t\t\t\tcitadel/addons\n": False}

            current_index = 0
            edit_index = 0
            for line in lines:
                if line.replace("\t", "").replace("\n", "") == target:
                    edit_index = current_index
                for edited_line in edited_lines:
                    if edited_line.replace("\t", "").replace("\n", "") == line.replace("\t", "").replace("\n", ""): #the edited line already exists
                        edited_lines[edited_line] = True
                current_index += 1
            for index, line in enumerate(edited_lines):
                if edited_lines[line] is False:
                    lines.insert(edit_index + index + 1, line)
            with open(game_info_file_path, "w") as f:
                f.writelines(lines)

            #remove all the currently installed mods
            shutil.rmtree(self.current_addon_directory)
            os.mkdir(self.current_addon_directory)

            #now copy the mods over
            written_mod_count = 0
            missing_file_paths_alert = False
            mod_list_index = 0
            mod_count = self.list_widget.count()
            while mod_list_index < mod_count:
                if written_mod_count >= MAXIMUM_MOD_AMOUNT:
                    QMessageBox.information(self, "Attention!", "Maximum mod limit reached! Only the first 99 enabled mods have been loaded.")
                    break
                item_widget = self.list_widget.itemWidget(self.list_widget.item(mod_list_index))
                if item_widget.toggle.isChecked():
                    try:
                        #copy the mod over to the game's addon directory, note the name must be of the form: "pakXX_dir.vpk"
                        os.link(item_widget.file_path, os.path.join(self.current_addon_directory, "pak" + "0"*(2 - len(str(written_mod_count + 1))) + str(written_mod_count + 1) + "_dir.vpk"))
                        written_mod_count += 1
                    except PermissionError:
                        QMessageBox.information(self, "Attention!", "If you are seeing this message, the mod manager can't load your mods because it needs administrator" \
                        "privileges to edit the game folder. Please run the application again as administrator.")
                    except:
                        #the mod does not exist anymore, delete it from the mod list and remove its file path
                        missing_file_paths_alert = True
                        item_widget.delete_self()
                        mod_count -= 1
                mod_list_index += 1
            if missing_file_paths_alert:
                QMessageBox.information(self, "Attention!", "The mod manager couldn't find some of your mod(s) (possibly deleted VPKs or changed filepaths). " \
                "They have been removed from the mod list, and the new configuration has been saved. All other selected mods have been loaded.")
        except PermissionError:
            QMessageBox.information(self, "Attention!", "If you are seeing this message, the mod manager can't load your mods because the game is open, " \
            "Please close the game if it is open.")
            return False
        return True

    def start_game(self) -> bool:
        '''
        Starts the game if the game folder is detected, otherwise displays an error message box.
        Returns True if the game started successfully, False if not.
        This may fail if Steam is not currently running.
        '''
        if self.game_files_found:
            try:
                os.startfile(self.current_game_executable_path)
            except:
                QMessageBox.information(self, "Attention!", "Could not start game due to an error. Check file permissions for the game folder or this application.")
                return False
            return True
        else:
            QMessageBox.information(self, "Attention!", "Could not start game, because the game folder could not be located!")
            return False

    def edit_game_folder_location(self) -> bool:
        '''
        Opens a file dialog to select a new game folder directory, and saves it to SETTINGS_FILE_PATH.
        Checks to see if the game folder actually contains the game executable and the addons folder, and
        changes the message at the bottom of the client to reflect the new status of the game folder (found/missing).
        Updates the global current paths and sets game_files_found to True if the game folder was found, but sets game_files_found to be False if the folder was not a valid game folder.
        Returns True if the folder selected was a valid game folder and was its path was successfully saved, False if not.
        '''
        folder = QFileDialog.getExistingDirectory(self, self.tr("Open Deadlock Directory"), "/home")

        if not folder: #user closed the dialog instead of selected
            return False
        
        if check_game_folder(folder): #valid game folder, contains addon folder and the actual game
            try:
                settings = {}
                with open(SETTINGS_FILE_PATH, "r", encoding="utf-8") as settings_file:
                    settings = json.load(settings_file)
                settings["game_folder_location"] = folder
                with open(SETTINGS_FILE_PATH, "w", encoding="utf-8") as settings_file:
                    json.dump(settings, settings_file, indent=JSON_INDENT_AMOUNT)
            except:
                QMessageBox.information(self, "Error", "Couldn't save game folder location!")
                return False
            
            self.found_game_files(folder) #this updates the global paths, and changes the light and message at the bottom of the client
            return True
        else:
            self.game_files_found = False

            #display a message box and an alert at the bottom of the screen
            QMessageBox.information(self, "Error", "Game folder not detected!")
            self.set_file_warning(False)

    def open_mod_browser(self) -> None:
        '''
        Creates and sets a new instance of the mod browser if one does not exist. Displays the old instance if it was running.
        Does not interrupt any ongoing downloads.
        '''
        if self.mod_browser:
            self.mod_browser.show()
        else:
            self.mod_browser = deadlock_mod_browser.ModBrowserWidget(self)
            self.mod_browser.show()
            self.mod_browser.raise_()

    def open_settings_menu(self) -> None:
        '''
        Creates and displays a new settings window. Destroys the old one, if it exists.
        '''
        import settings_window
        if self.settings_menu:
            self.settings_menu.close()
            self.settings_menu.deleteLater()
        self.settings_menu = settings_window.SettingsMenuWidget(self)
        self.settings_menu.show()
        self.settings_menu.raise_()
    
    def open_application_directory(self) -> None:
        '''
        Opens the application directory, which stores all downloaded and extracted mods, and the settings file.
        '''
        QFileDialog.getOpenFileName(self, "Files", APPLICATION_DIRECTORY, "All Files (*)" )

    def closeEvent(self, event: QCloseEvent) -> None:
        '''
        Override for closing the window. Ensures the mod browser (and its subwidgets as well) are properly closed and cleaned up.
        '''
        with self.worker_thread_lock:
            if self.workers_and_threads:
                msg_box = QMessageBox()
                msg_box.setWindowTitle("Warning!")
                msg_box.setText("You have ongoing downloads! Exiting now might cause unexpected issues. Are you sure you want to quit?")
                msg_box.setIcon(QMessageBox.Question)
                msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
                response = msg_box.exec_()
                if response != QMessageBox.Yes: #if the user clicked no or closed the message box
                    event.ignore()
                    return

        if self.mod_browser:
            self.mod_browser.clear_catalogue()
            self.mod_browser.close()
            self.mod_browser.deleteLater()

        if self.settings_menu:
            self.settings_menu.close()
            self.settings_menu.deleteLater()

        event.accept()
    
class NumberedModListWidget(QListWidget):
    '''
    Custom list widget that enables drag and drop capabilities and automatic renumbering, for altering the load order of mods.
    '''
    def __init__(self, main_window: ModManager):
        '''
        main_window should be an instance of ModManager. List items cannot be moved outside the list, and multiple items cannot be selected.
        '''
        super().__init__()
        self.setObjectName("modlist")
        self.setSelectionMode(QListWidget.SingleSelection)
        self.setDragDropMode(QListWidget.InternalMove)
        self.main_window = main_window

    def dropEvent(self, event: QDropEvent) -> None:
        '''
        Override for when items are drag and dropped. Renumbers the mod list and saves the new load order to the configuration file.
        '''
        super().dropEvent(event)
        self.renumber_items()
        self.main_window.save_profile()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        '''
        Override needed because of a pyqt5 bug with embedded widgets in qlists
        See explanation and solution here: https://stackoverflow.com/questions/74263946/widget-inside-qlistwidgetitem-disappears-after-internal-move
        '''
        target_row = self.row(self.itemAt(event.pos()))
        current_row = self.currentRow()
        
        if (target_row == current_row + 1) or (current_row == self.count() - 1 and target_row == -1):
            event.ignore()
        else:
            super().dragMoveEvent(event)

    def renumber_items(self) -> None:
        '''
        Edits the labels of every entry to contain their place in the mod list. 
        This is called upon mods being reordered via the GUI's drag and drop, or when new mods are added.
        '''
        for i in range(self.count()):
            item = self.item(i)
            item_widget = self.itemWidget(item)
            item_widget.number = i + 1
            item_widget.label.setText(f"{item_widget.number}. {item_widget.name}")

class ModListItem(QWidget):
    '''
    Custom list item widget for individual mods that supports holding nicknames, file paths, mod on/off toggle, and a self-removal button.
    '''
    def __init__(self, name: str, file_path: str, list_widget: NumberedModListWidget, main_window: ModManager, number: int, from_gamebanana: bool=False) -> None:
        super().__init__() 
        self.list_widget = list_widget
        self.name = name
        self.file_path = file_path
        self.main_window = main_window #this should always be the mod manager window
        self.number = number #position in the mod list, index begins at 1
        self.from_gamebanana = from_gamebanana

        self.setObjectName("#modlist-item")
        layout = QHBoxLayout()

        #mod name
        self.label = QLabel(f"{self.number}. " + name)
        self.label.setObjectName("mod-name")
        layout.addWidget(self.label)

        self.line_edit = QLineEdit("")
        self.line_edit.setPlaceholderText("Mod name...")
        self.line_edit.setText(name)
        self.line_edit.returnPressed.connect(self.rename_mod)
        self.line_edit.setVisible(False)
        layout.addWidget(self.line_edit)

        if from_gamebanana:
            self.gamebanana_logo = QLabel("🍌")
            layout.addWidget(self.gamebanana_logo)

        layout.addStretch() #this puts the buttons on the right

        self.rename_button = QPushButton("✍️")
        self.rename_button.setObjectName("rename-button")
        self.rename_button.setFixedSize(20, 20)
        self.rename_button.clicked.connect(lambda: (self.line_edit.setVisible(True), self.rename_button.setVisible(False), self.label.setVisible(False), self.line_edit.setFocus()))
        layout.addWidget(self.rename_button)

        #checkbox for marking the mods as enabled/disabled
        self.toggle = QCheckBox()
        self.toggle.setChecked(True)
        self.toggle.stateChanged.connect(lambda: self.main_window.save_profile() if self.main_window.finished_initial_load else None) #only save the config if finished loading
        
        layout.addWidget(self.toggle)

        #the remove button for mods
        self.remove_button = QPushButton("X", self)
        self.remove_button.setFixedWidth(20)
        self.remove_button.setFixedHeight(20)
        self.remove_button.clicked.connect(self.confirm_deletion) #deletes the mod from the list along with the actual file path if possible, after confirmation
        layout.addWidget(self.remove_button)

        self.setLayout(layout)

    def confirm_deletion(self) -> None:
        '''
        Ask the user to confirm if they wish to delete this mod, and only delete it if the user clicks Yes.
        '''
        msg_box = QMessageBox()
        path_to_icon = get_resource_path(WINDOW_ICON_PATH_SUFFIX)
        msg_box.setWindowIcon(QIcon(path_to_icon))
        msg_box.setWindowTitle("Wait!")
        msg_box.setText("Delete this mod?")
        msg_box.setIcon(QMessageBox.Question)
        msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        response = msg_box.exec_()
        if response != QMessageBox.Yes: #if the user clicked no or closed the message box
            return
        else:
            self.delete_self()

    def rename_mod(self) -> None:
        '''
        Renames the mod according to the mod's line editor's text, if it is non-empty. Makes the label and rename button visible again, and the line edit invisible.
        '''
        self.label.setVisible(True)
        self.line_edit.setVisible(False)
        self.rename_button.setVisible(True)
        if self.line_edit.text():
            self.name = self.line_edit.text()
            self.label.setText(str(self.number) + ". " + self.line_edit.text())
            self.line_edit.setText(self.name)
            self.main_window.save_profile()

    def add_to_list(self, list_item: QListWidget) -> None:
        '''
        Binds the item_widget to the QListWidget instead of just the text, then adds it to the list_widget.
        list_item should be created with the list_widget as a parent, like this: QListWidgetItem(self.list_widget)
        '''
        list_item.setSizeHint(self.sizeHint())
        self.list_widget.addItem(list_item)
        self.list_widget.setItemWidget(list_item, self)

    def delete_self(self) -> None:
        '''
        Deletes list item by indexing itself from its name and taking the item from the parent.
        Deletes the mod (.vpk file) and folder (if empty) containing the mod at self.file_path.
        '''
        if self.list_widget:
            index = self.number - 1
            self.list_widget.takeItem(index)
            self.list_widget.renumber_items()
            delete_path_and_parent_recursive(self.file_path)
            self.main_window.save_profile() #save to the configuration file

if __name__ == "__main__":
    os.makedirs(APPLICATION_DIRECTORY, exist_ok=True) #create the directory for our application so we don't have to later
    if not os.path.exists(APPLICATION_DIRECTORY):
        raise FileNotFoundError(errno.ENOENT, "Could not create the application directory. Please allow permissions to create folders and write to files.")
    
    app = QApplication(sys.argv)
    window = ModManager()

    #load the fonts from the resource folder
    path_to_fonts = get_resource_path(FONTS_PATH_SUFFIX)
    for font in os.listdir(path_to_fonts):
        QFontDatabase.addApplicationFont(os.path.join(path_to_fonts, font))
    path_to_stylesheet = get_resource_path(STYLE_PATH_SUFFIX)
    with open(path_to_stylesheet, "r") as f:
        qss = f.read()
    app.setStyleSheet(qss)

    window.show()
    window.raise_()
    sys.exit(app.exec_())