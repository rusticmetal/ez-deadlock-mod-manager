from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QFileDialog, QMessageBox)
from PyQt5.QtGui import QIcon

import json
import rarfile

from constants import *
from EZDeadlockModManager import ModManager

class SettingsMenuWidget(QWidget):
    '''
    The settings menu. Contains various buttons for configuring settings and utilities.
    '''
    def __init__(self, main_window: ModManager):
        super().__init__()
        self.main_window = main_window

        self.layout = QVBoxLayout(self)
        self.setGeometry(1000, 200, 100, 100)
        self.setWindowTitle("Settings")
        path_to_icon = get_resource_path(WINDOW_ICON_PATH_SUFFIX)
        self.setWindowIcon(QIcon(path_to_icon))
        self.setObjectName("settings")

        self.change_game_button = QPushButton("Change Game Folder Location (Select the 'Deadlock' Folder!)")
        self.change_game_button.clicked.connect(main_window.edit_game_folder_location)
        self.layout.addWidget(self.change_game_button)

        self.view_folder_button = QPushButton("View Mods in File Explorer")
        self.view_folder_button.clicked.connect(main_window.open_application_directory)
        self.layout.addWidget(self.view_folder_button)

        self.find_unrar_tool_button = QPushButton("Set .rar tool location")
        self.find_unrar_tool_button.clicked.connect(self.set_rar_tool)
        self.layout.addWidget(self.find_unrar_tool_button)

        self.scan_for_mods_button = QPushButton("Scan for mods (Use this if modlist breaks or if downloaded mods \nare missing, will reset all mod nicknames!)")
        self.scan_for_mods_button.clicked.connect(self.scan_for_mods)
        self.layout.addWidget(self.scan_for_mods_button)

        self.layout.addStretch()

    def set_rar_tool(self) -> bool:
        '''
        Opens a file dialog and sets the rar tool path in the settings file to the file specified.
        Returns True if set and saved successfully, False if not. Does not verify that rar tool is actually a rar tool or if it works.
        '''
        tool_location, _ = QFileDialog.getOpenFileName(self, self.tr("Locate rar file tool"), "/home")
        if tool_location:
            try:
                settings = {}
                with open(SETTINGS_FILE_PATH, "r", encoding="utf-8") as settings_file:
                    settings = json.load(settings_file)
                settings["rar_tool_location"] = tool_location
                with open(SETTINGS_FILE_PATH, "w", encoding="utf-8") as settings_file:
                    json.dump(settings, settings_file, indent=JSON_INDENT_AMOUNT)
                rarfile.UNRAR_TOOL = tool_location
                self.main_window.rar_tool_found = True
            except:
               QMessageBox(self, "Error", "Could not save rar tool location to settings file.")
        
    def scan_for_mods(self) -> None:
        '''
        Recreates the entire settings file. Attempts to parse the typical directories for mods installed via the mod browser or manually, 
        and adds them back to the settings file mod list. Wipes any existing mods from the settings file in order to re-add them, meaning mod nicknames are reset.
        Finally, loads the mod list from the newly created settings.
        '''
        settings = {}
        if os.path.exists(SETTINGS_FILE_PATH):
            with open(SETTINGS_FILE_PATH, "r", encoding="utf-8") as settings_file:
                settings = json.load(settings_file)
        else:
            settings["game_folder_location"] = ""
            settings["rar_tool_location"] = ""
        settings["mods"] = []

        for directory in [MOD_DIRECTORY, SOUND_DIRECTORY, VPK_DIRECTORY]:
            for mod_number in os.listdir(directory):
                if os.path.isdir(os.path.join(directory, mod_number)):
                    for root, dirs, files in os.walk(os.path.join(directory, mod_number)):
                        for name in files:
                            if ".vpk" in name:
                                mod = {}
                                mod["name"] = os.path.join(root, name)
                                mod["file_path"] = os.path.join(root, name)
                                mod["toggled_on"] = True
                                if directory != VPK_DIRECTORY:
                                    mod["from_gamebanana"] = True
                                    if directory == SOUND_DIRECTORY:
                                        mod["link"] = "https://gamebanana.com/sounds/" + str(mod_number)
                                    else:
                                        mod["link"] = "https://gamebanana.com/mods/" + str(mod_number)
                                else:
                                    mod["from_gamebanana"] = False
                                settings["mods"].append(mod)
                elif ".vpk" in os.path.join(directory, mod_number): #manually added mods can be either .vpk within folders or just .vpk, so we need to check
                    mod = {}
                    mod["name"] = os.path.join(directory, mod_number)
                    mod["file_path"] = os.path.join(directory, mod_number)
                    mod["toggled_on"] = True
                    mod["from_gamebanana"] = False
                    settings["mods"].append(mod)

        with open(SETTINGS_FILE_PATH, "w", encoding="utf-8") as settings_file:
            json.dump(settings, settings_file, indent=JSON_INDENT_AMOUNT)

        self.main_window.read_profile() #load the mods back into the list