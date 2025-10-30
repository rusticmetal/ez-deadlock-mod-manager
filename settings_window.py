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

        self.view_folder_button = QPushButton("View Application Folder")
        self.view_folder_button.clicked.connect(main_window.open_application_directory)
        self.layout.addWidget(self.view_folder_button)

        self.find_unrar_tool_button = QPushButton("Set .rar tool")
        self.find_unrar_tool_button.clicked.connect(self.set_rar_tool)
        self.layout.addWidget(self.find_unrar_tool_button)

        #TODO: button to scan for downloaded mods here and rebuild modpack file
        #TODO: button to delete old download folders if they exist

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