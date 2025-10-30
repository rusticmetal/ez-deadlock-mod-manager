from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QMessageBox)
from PyQt5.QtGui import (QPixmap, QIcon, QColor, QCloseEvent)
from PyQt5.QtCore import (Qt, QObject, QThread, pyqtSignal, QUrl)
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent

import requests

import os
import webbrowser
import tempfile

from constants import *
from EZDeadlockModManager import ModManager
from deadlock_mod_downloader import download_mods

RESULT_ITEM_DIMENSIONS = [240, 225]
FEATURED_BORDER = "2px solid green"
IMAGE_WIDTH = 200
IMAGE_HEIGHT = 100
TRANSPARENT_IMAGE_COLOUR = QColor(0, 0, 0, 0)
MAX_ONGOING_DOWNLOADS = 5

def load_image_from_url(url: str) -> QPixmap:
    '''
    Fetches an image via a GET request to the url. Creates and returns a pixmap object containing the downloaded image.
    If the response does not contain any content, return a transparent pixmap.
    '''
    if not url:
        blank_pixmap = QPixmap(IMAGE_WIDTH, IMAGE_HEIGHT)
        blank_pixmap.fill(TRANSPARENT_IMAGE_COLOUR)
        return blank_pixmap
    try:
        response = requests.get(url, timeout=RESPONSE_WAIT_TIME)
        if response.status_code != 200:
            response.raise_for_status()
        else:
            pixmap = QPixmap()
            pixmap.loadFromData(response.content)
            return pixmap
    except:
        blank_pixmap = QPixmap(IMAGE_WIDTH, IMAGE_HEIGHT)
        blank_pixmap.fill(TRANSPARENT_IMAGE_COLOUR)
        return blank_pixmap

class SoundPreviewWidget(QWidget):
    '''
    Custom sound preview widget for mods that alter game sound effects.
    Fetches the sound clip at the url only when first played, and toggles the playing state when clicked.
    Note: needs the actual file's path, not the mod page.
    '''
    def __init__(self, url:str) -> None:
        '''
        The preview widget only consists of the toggle button and the underlying media player, 
        along with the class attributes needed for it to fetch and store the sound effects.
        '''
        super().__init__()

        layout = QVBoxLayout()

        self.url = url
        self.sound_file = None
        self.sound_file_loaded = False

        #toggle button
        self.play_pause_button = QPushButton("Preview Sound ♪")
        self.play_pause_button.setObjectName("sound-preview")
        self.play_pause_button.clicked.connect(self._toggle_playback)
        layout.addWidget(self.play_pause_button)

        self.setLayout(layout)

        #media player
        self.player = QMediaPlayer(parent=self)
        self.player.setVolume(20)
        self.player.stateChanged.connect(self._update_button) #update the button's text when the sound is toggled

    def _load_sound_file(self) -> bool:
        '''
        Fetches the sound file from the url, saves it as a temporary file and loads the sound file into the media player.
        Returns True if successfully loaded, False if it failed to fetch the file or load to the media player.
        '''
        try:
            response = requests.get(self.url, timeout=RESPONSE_WAIT_TIME)
        except:
            print("Failed to download sound file.")
            return False
        if response.status_code != 200:
            print("Failed to download sound file.")
            return False

        try:
            #get a temporary filename for the file and save it, note that it is removed upon closing the widget
            self.sound_file = tempfile.NamedTemporaryFile(delete=False)
            self.sound_file.write(response.content)
            self.sound_file.close()

            #finally load the sound file from its temporary path
            file_path = QUrl.fromLocalFile(self.sound_file.name)
            self.player.setMedia(QMediaContent(file_path))
            self.sound_file_loaded = True
            return True
        
        except Exception as e:
            print("Failed to load sound file: " + str(e))

    def _toggle_playback(self) -> bool:
        '''
        Toggles the playing state of the media player's sound file. Attempts to load the file if not currently already loaded.
        Returns True unless the sound file could not be loaded.
        '''
        if not self.sound_file_loaded:
            if not self._load_sound_file():
                return False

        if self.player.state() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()
        return True

    def _update_button(self, state: QMediaPlayer.State) -> None:
        '''
        Update's the toggle button's text based on the media player's current playing state.
        '''
        if state == QMediaPlayer.PlayingState:
            self.play_pause_button.setText("Pause ⏸")
        else:
            self.play_pause_button.setText("Preview Sound ♪")

    def closeEvent(self, event: QCloseEvent) -> None:
        '''
        Override for when the widget is closed. Note that since this widget is never opened as a window, .close() must be called on the widget for this to trigger.
        Pauses the player if it is currently playing, and then removes the temporary sound file.
        '''
        if self.player.state() == QMediaPlayer.PlayingState:
            self.player.pause()

        if self.sound_file:
            try:
                os.remove(self.sound_file.name)
            except Exception as e:
                print("Failed to delete temporary sound file: " + str(e))
        event.accept()

class DownloadWorker(QObject):
    '''
    Worker object to support concurrency when downloading mods. Instantiate this and a QThread object and bind them together,
    and don't forget to set the start and end behaviour for both the worker and the thread, see _start_download_thread() below.
    link should be the actual mod page, like: "https://gamebanana.com/sounds/79236". These are fetched when the mod browser searches, and are stored in the SearchResultItemWidget.
    mod_name is simply the name of the mod as it appears on the mod page.
    '''
    finished = pyqtSignal(list, ModManager, str, str, int, bool) #see _handle_downloaded_mods()

    def __init__(self, main_window: ModManager, link: str, mod_name: str, item_type: str, number: int) -> None:
        super().__init__()
        self.main_window = main_window
        self.link = link
        self.mod_name = mod_name
        self.item_type = item_type
        self.number = number

    def run(self):
        '''
        This is what should occur when the thread is started (assuming it is bound to the worker). See download_mods() in the mod_downloader module.
        '''
        file_paths, mods_downloaded_successfully = download_mods(self.link, self.main_window.mod_browser.download_scraper)
        #note: mod name cannot have commas due to how information is stored in the modpack file
        self.finished.emit(file_paths, self.main_window, self.mod_name.replace(",", ""), self.item_type, self.number, mods_downloaded_successfully) #this triggers _handle_downloaded_mods()

def _start_download_thread(main_window: ModManager, mod_page_link: str, mod_name: str, item_type: str, number: int) -> None:
    '''
    Called when clicking the download button for a mod in the mod browser. Creates and starts a QThread that downloads the mod at the link's mod page.
    Handles adding to the mod manager's mod list in a concurrent manner, setting the mods to be added only after being given the signal when the worker is finished.
    Requires main_window.worker_thread_lock to eventually become available to start executing the thread.
    '''
    with main_window.worker_thread_lock:
        main_window.download_warning_widget.setVisible(True) #lets the user know there are mods currently downloading

        if (number, item_type) in main_window.workers_and_threads:
            msg_box = QMessageBox()
            msg_box.setWindowTitle("Alert!")
            path_to_icon = get_resource_path(WINDOW_ICON_PATH_SUFFIX)
            msg_box.setWindowIcon(QIcon(path_to_icon))
            msg_box.setText("You are already downloading this mod!")
            msg_box.exec_()
            return

        if len(main_window.workers_and_threads) >= MAX_ONGOING_DOWNLOADS:
            msg_box = QMessageBox()
            msg_box.setWindowTitle("Alert!")
            path_to_icon = get_resource_path(WINDOW_ICON_PATH_SUFFIX)
            msg_box.setWindowIcon(QIcon(path_to_icon))
            msg_box.setText("Too many ongoing downloads (5)!")
            msg_box.exec_()
            return

        #now create the thread and worker function, and set their references
        thread = QThread()
        worker = DownloadWorker(main_window, mod_page_link, mod_name, item_type, number)
        worker.moveToThread(thread) #bind the worker to the thread
        main_window.workers_and_threads[(number, item_type)] = (worker, thread) #this is crucial as to not lose the memory addresses of the threads, otherwise we will crash

    thread.started.connect(worker.run) #this actually downloads the mods, see DownloadWorker.run()
    worker.finished.connect(_handle_downloaded_mods) #adds the mods to our mod list in the mod manager and deletes the temporary files/folders
    thread.finished.connect(lambda: _cleanup_download_thread(main_window, number, item_type)) #this will delete the references in memory to the thread
    worker.finished.connect(thread.quit)

    worker.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)

    thread.start()

def _handle_downloaded_mods(file_paths: list[str], main_window: ModManager, 
                            mod_name: str, item_type: str, number: int, mods_downloaded_successfully: bool) -> None:
    '''
    Adds the mods concurrently (if downloaded successfully). Removes them from the paths they were originally downloaded to, and deletes their temporary parent directory.
    This function is to be bound to the worker when it is finished, and never to be called explicitly.
    '''
    if not mods_downloaded_successfully:
        QMessageBox.information(main_window, "Error", "Failed to download one or more mods.")
    if file_paths:
        main_window.add_mod(file_paths, mod_name, item_type, number)

    for file in file_paths:
        try:
            os.remove(file)
        except:
            print("Error, could not delete temporary file.")
    if file_paths:
        parent_directory = os.path.dirname(file_paths[0]) #all downloaded files in a thread have the same parent directory, so this is fine
        if not os.listdir(parent_directory): #empty so now we clean up the folder
            try:
                os.rmdir(parent_directory)
            except:
                print("Error, could not delete: Directory is not empty or invalid permissions.")
            
def _cleanup_download_thread(main_window: ModManager, download_num: int, item_type: str) -> None:
    '''
    Concurrently deletes the references to the worker and thread that correspond with the download number.
    Also removes the download warning if this happens to be the only download thread remaining.
    Requires main_window.worker_thread_lock to execute.
    This function is to be bound to the thread upon finishing, and never to be called explicitly.
    '''
    with main_window.worker_thread_lock:
        del main_window.workers_and_threads[(download_num, item_type)]
        print((download_num, item_type))
        if not main_window.workers_and_threads:
            main_window.download_warning_widget.setVisible(False)

class SearchResultItemWidget(QWidget):
    '''
    Widget for items that appear in the catalogue when the mod browser's search is triggered. Currently features
    a title label, a details button that links straight to the mod page in a web browser, a download button, and
    media preview based on a link to a file (image previews for mods and a sound preview for sound effects).
    '''
    def __init__(self, main_window: ModManager, mod_name: str, item_type: str, number: int, link: str, media: str=""):
        super().__init__()
        self.main_window = main_window
        self.mod_name = mod_name
        self.item_type = item_type #"Mod" or "Sound" are supported currently for downloading, "Request" or others should not be downloaded
        self.number = number #mod or sound number
        self.link = link #this goes to the mod page
        self.media = media #first image for mod or sound preview for sound effects

        '''
        These attributes are purely cosmetic (not used for downloading, and they do not affect other parts of the program).
        Set them using the appropriate setter functions after instantiation.
        '''
        self.submitter = ""
        self.submitter_url = ""
        self.visible_preview = False
        self.likes = 0
        self.views = 0
        self.featured = False

        layout = QVBoxLayout()
        self.setContentsMargins(5, 10, 5, 10)

        #mod title
        self.name_label = QLabel(mod_name)
        self.name_label.setObjectName("mod-title")
        self.name_label.setAlignment(Qt.AlignCenter)
        self.name_label.setWordWrap(True)
        layout.addWidget(self.name_label)

        layout.addStretch()

        #add either a sound or image preview
        _, media_file_extension = os.path.splitext(media)
        if media_file_extension == ".mp3" or media_file_extension == ".wav" or media_file_extension == ".ogg":
            layout.addWidget(SoundPreviewWidget(media))
        else:
            label = QLabel()
            label.setObjectName("thumbnail")
            label.setPixmap(load_image_from_url(media)) #this loads a transparent image if no media link is given
            label.setScaledContents(True)
            layout.addWidget(label)

        layout.addStretch()

        #submitter/author
        self.submitter_link = QPushButton("By :")
        self.submitter_link.setObjectName("submitter-link")
        layout.addWidget(self.submitter_link)

        info_layout = QHBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)

        #details (links to gamebanana in a web browser) and individual mod statistics
        details_button = QPushButton("🌐 Details") #this will direct you to the mod page within a web browser
        details_button.setObjectName("details-button")
        details_button.clicked.connect(lambda: webbrowser.open_new_tab(self.link))
        info_layout.addWidget(details_button)

        info_layout.addStretch()

        self.like_count_label = QLabel("♥ 0")
        self.like_count_label.setObjectName("info-label")
        info_layout.addWidget(self.like_count_label)

        self.view_count_label = QLabel("👁 0")
        self.view_count_label.setObjectName("info-label")
        info_layout.addWidget(self.view_count_label)

        self.post_count_label = QLabel("🗨 0")
        self.post_count_label.setObjectName("info-label")
        info_layout.addWidget(self.post_count_label)

        layout.addLayout(info_layout)

        #download button
        if item_type == "Mod" or item_type == "Sound": #don't add the download button for requests/concepts/threads or any other item types
            self.download_button = QPushButton("Download  ↓")
            self.download_button.setObjectName("download-button")
            self.download_button.clicked.connect(lambda: _start_download_thread(main_window, link, mod_name, item_type, number))
            layout.addWidget(self.download_button)

        self.setFixedSize(*RESULT_ITEM_DIMENSIONS)
        self.setLayout(layout)

    def set_media(self, media_url: str):
        self.media = media_url
    
    def set_submitter(self, submitter: str, submitter_url=""):
        self.submitter = submitter
        self.submitter_url = submitter_url
        self.submitter_link.setText("By : " + submitter)
        self.submitter_link.clicked.connect(lambda: webbrowser.open_new_tab(submitter_url))

    def set_preview_visibility(self, visibility: bool):
        self.visible_preview = visibility

    def set_likes(self, like_count: int):
        self.likes = like_count
        self.like_count_label.setText("♥ " + str(like_count))

    def set_views(self, view_count: int):
        self.views = view_count
        self.view_count_label.setText("👁 " + str(view_count))
    
    def set_posts(self, post_count: int):
        self.posts = post_count
        self.post_count_label.setText("🗨 " + str(post_count))

    def set_featured_status(self, featured: bool):
        self.featured = featured
        if featured:
            self.name_label.setStyleSheet(f"border: {FEATURED_BORDER};")