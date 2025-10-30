from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QLineEdit, QLabel, QHBoxLayout, QGridLayout)
from PyQt5.QtGui import (QIcon, QCloseEvent)

import cloudscraper

from constants import *
from EZDeadlockModManager import ModManager
from deadlock_mod_browser_features import (Paginate, SearchResultItemWidget)

MOD_BROWSER_DIMENSIONS = [150, 150, 800, 500]
ITEMS_PER_PAGE = 15
COLUMNS = 5
GAMEBANANA_BASE_GAME_URL = "https://gamebanana.com/apiv11/Game/20948/Subfeed?&_csvModelInclusions=Mod,Sound&_nPerpage=15&_nPage=" #must append a page number immediately after, also requires '_sSort' to be set in the url as well
SORT_NEW_PARAMETER = "&_sSort=new"
SORT_DEFAULT_PARAMETER = "&_sSort=default"
SORT_UPDATED_PARAMETER = "&_sSort=updated"

'''
Check the postman documentation for the api here: https://www.postman.com/s0nought/gb-api-v11/request/ufm61ja/advanced-search?tab=overview
Another possible useful api is this: https://api.gamebanana.com/
This also seemed useful but didn't end up being used: https://github.com/robinxoxo/pybanana

Note: Filtering mods in the browser by character category does not seem to be possible with the API, so the search terms will have to suffice 
(the API does return a category, but its a general category like "Skins" or "Model Replacement", not the character's category).
'''

class ModBrowserWidget(QWidget):
    '''
    The mod browser window. Contains a search bar and a grid layout capable of displaying SearchResultItemWidgets.
    '''
    def __init__(self, main_window: ModManager):
        super().__init__()
        
        self.main_window = main_window
        self.current_page = 1 #used for cataloguing the search items, page indexes starts at 1

        layout = QVBoxLayout(self)
        self.setGeometry(*MOD_BROWSER_DIMENSIONS)
        self.setWindowTitle("Mod Browser")
        path_to_icon = get_resource_path(WINDOW_ICON_PATH_SUFFIX)
        self.setWindowIcon(QIcon(path_to_icon))
        self.setObjectName("mod-browser")

        #search bar
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search for mods here!")
        self.search_bar.returnPressed.connect(lambda: self.search(Paginate.DO_NOT_PAGINATE))
        layout.addWidget(self.search_bar)

        #the grid will hold our search items in a catalogue style
        self.search_item_container = QWidget()
        self.grid_layout = QGridLayout(self.search_item_container)
        layout.addWidget(self.search_item_container)

        #buttons to flip through search pages
        button_layout = QHBoxLayout()
        self.prev_button = QPushButton("Previous")
        self.prev_button.clicked.connect(lambda: self.search(Paginate.PREVIOUS_PAGE))

        self.next_button = QPushButton("Next")
        self.page_label = QLabel()
        self.next_button.clicked.connect(lambda: self.search(Paginate.NEXT_PAGE))
        
        #add the buttons with a placeholder in the middle to space them out on the left and right
        button_layout.addWidget(self.prev_button)
        button_layout.addStretch()
        button_layout.addWidget(self.page_label)
        button_layout.addStretch()
        button_layout.addWidget(self.next_button)

        layout.addLayout(button_layout)

        self.scraper = cloudscraper.create_scraper()
        self.download_scraper = cloudscraper.create_scraper() #this one is for multithreading

        self.search(Paginate.DO_NOT_PAGINATE) #display the newest mods

    def search(self, pagination: Paginate=Paginate.DO_NOT_PAGINATE) -> bool:
        '''
        Search and display mods similar to the query in the search bar. Does not display mods for queries that are 1-2 characters long.
        If the search bar is empty (0 character query), displays the newest mods for the game without a name restriction.
        Returns True if the request was successful and the catalogue was populated, False if either fails.
        Currently only sorts by newest entries first.
        Executed upon pressing Enter when interacting with the search bar.
        '''
        query = self.search_bar.text().lower()
        if len(query) > 0 and len(query) < 3:
            return False

        match pagination:
            case Paginate.DO_NOT_PAGINATE:
                self.current_page = 1

            case Paginate.PREVIOUS_PAGE:
                if self.current_page > 1:
                    self.current_page -= 1
                else:
                    return False
                
            case Paginate.NEXT_PAGE:
                self.current_page += 1

        if len(query) >= 3: #show the newest mods with the keyword
            url = GAMEBANANA_BASE_GAME_URL + str(self.current_page) + SORT_NEW_PARAMETER + "&_sName=" + query
        else: #show all the newest mods
            url = GAMEBANANA_BASE_GAME_URL + str(self.current_page) + SORT_NEW_PARAMETER       
    
        response = self.scraper.get(url)
        try:
            response_data = response.json()
        except ValueError:
            # TODO: maybe close the mod browser object
            response_data = {}
            return self.update_catalogue(response_data)

        #this just makes sure we don't mess up our current page and catalogue if there isn't a next page to load
        if pagination == Paginate.NEXT_PAGE and not response_data['_aRecords']:
            self.current_page -= 1
            return False
        
        #update the catalogue based on the new page that was fetched
        return self.update_catalogue(response_data)
    
    def clear_catalogue(self) -> None:
        '''
        Deletes all previously loaded items, starting with the end of the catalogue first.
        Call this before propagating the catalogue with new entries, or when deleting the search item container or mod browser.
        '''
        for i in reversed(range(self.grid_layout.count())):
            item_widget = self.grid_layout.itemAt(i).widget()
            if item_widget:
                item_widget.setParent(None)
                item_widget.close()
                item_widget.deleteLater()

    def update_catalogue(self, response_data: dict) -> bool:
        '''
        Updates the results in the catalogue based on the entries retrieved from the response data.
        Deletes all other items that were previously loaded.
        Does not alter anything if the response data is incorrect (does not contain records). Does not display obsolete mods.
        Returns True unless the response_data is incorrect, which in that case returns False.
        '''
        if not response_data:
            return False
        if '_aRecords' not in response_data: #just in case something was wrong about the query
            return False

        self.clear_catalogue()

        for idx, item in enumerate(response_data['_aRecords']):
            #propagate the catalogue left to right first
            row = idx // COLUMNS
            col = idx % COLUMNS
            try:
                if item['_bIsObsolete']: #don't let the user see or download obselete mods, they don't work anyways
                    continue

                match item['_sModelName']: #create and add a new item to the catalogue, with custom parameters according to the item type
                    case "Mod":
                        widget = SearchResultItemWidget(self.main_window,
                            item['_sName'], item['_sModelName'], item['_idRow'], item['_sProfileUrl'],
                            item['_aPreviewMedia']['_aImages'][0]['_sBaseUrl'] + '/' + item['_aPreviewMedia']['_aImages'][0]['_sFile220']) #the first image is the media

                    case "Sound":
                        widget = SearchResultItemWidget(self.main_window,
                            item['_sName'], item['_sModelName'], item['_idRow'], item['_sProfileUrl'], 
                            item['_aPreviewMedia']['_aMetadata']['_sAudioUrl']) #the sound preview is the media

                    case _:
                        '''
                        Concepts/Threads/Questions/Requests/Scripts/Sprays/Tools/Tutorials/WiPs
                        '''
                        widget = SearchResultItemWidget(self.main_window,
                             item['_sName'], item['_sModelName'], item['_idRow'], item['_sProfileUrl']) #note: no media is passed
                        
                widget.set_submitter(item['_aSubmitter']['_sName'], item['_aSubmitter']['_sProfileUrl'])
                if item['_sInitialVisibility'] == "show":
                    widget.set_preview_visibility(True)
                else:
                    widget.set_preview_visibility(False)

                if '_nLikeCount' in item:
                    widget.set_likes(item['_nLikeCount'])
                else:
                    widget.set_likes(0)
                if '_nViewCount' in item:
                    widget.set_views(item['_nViewCount'])
                else:
                    widget.set_views(0)
                if '_nPostCount' in item:
                    widget.set_posts(item['_nPostCount'])
                else:
                    widget.set_posts(0)
                widget.set_featured_status(item['_bWasFeatured'])

                self.grid_layout.addWidget(widget, row, col)
            except: #just in case the response has missing information
                continue
        return True

    def closeEvent(self, event: QCloseEvent) -> None:
        '''
        Override for closing the mod browser window. Simply hides the browser from view.
        Called when the user manually closes the mod browser window, and when the mod manager closes as well.
        The catalogue is manually deleted along with the other widgets in this window when the main mod manager is closed, not when this window is closed.
        '''
        self.hide()
        event.accept()