from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions
from selenium.common.exceptions import TimeoutException

from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from webdriver_manager.chrome import ChromeDriverManager

from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from webdriver_manager.firefox import GeckoDriverManager

from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.edge.options import Options as EdgeOptions

import cloudscraper

from typing import Protocol
import shutil
import os
import tempfile
import time

try:
    import winreg
    WINREG_IMPORTED = True
except ImportError: #this is thrown when executed on any os that isn't windows
    WINREG_IMPORTED = False

from constants import *

PAGE_LOADING_WAIT_TIME = 5 #time spent waiting for webdriver pages to load, in seconds
DOWNLOAD_CHUNK_SIZE = 8192
DOWNLOAD_LINK_CSS_SELECTOR = "a.DownloadLink.GreenColor"
NSFW_CONTENT_BUTTON_CSS_SELECTOR = "button.ShowNsfwContentButton"
UP_TO_DATE_MOD_LIST_CSS_SELECTOR = "ul.Flow.Files"
DOWNLOAD_PAGE_MOD_LINKS_CSS_SELECTOR = "li.File.Flow > div.Cluster.DownloadOptions > a.DownloadLink.GreenColor"
DOWNLOAD_PAGE_MOD_NAMES_CSS_SELECTOR = "li.File.Flow > div.Cluster > span.FileName"

#the order of these is important, whatever browser found first is used
WINDOWS_BROWSER_REGISTRY_PATHS = {
            "chrome": [r"SOFTWARE\\Microsoft\Windows\\CurrentVersion\App Paths\\chrome.exe",
            r"SOFTWARE\WOW6432Node\\Microsoft\Windows\\CurrentVersion\App Paths\\chrome.exe"],
            
            "firefox": [r"SOFTWARE\\Microsoft\Windows\\CurrentVersion\App Paths\\firefox.exe",
            r"SOFTWARE\WOW6432Node\\Microsoft\Windows\\CurrentVersion\App Paths\\firefox.exe"],

            "edge": [r"SOFTWARE\\Microsoft\Windows\\CurrentVersion\App Paths\\msedge.exe",
            r"SOFTWARE\WOW6432Node\\Microsoft\Windows\\CurrentVersion\App Paths\\msedge.exe"],
        }
BROWSER_PATHS =  {
            "chrome": shutil.which("google-chrome") or shutil.which("chrome") or shutil.which("chromium"),
            "firefox": shutil.which("firefox"),
            "edge": shutil.which("microsoft-edge") or shutil.which("msedge")
        }

'''
Note: This code only works for users with Chrome, Firefox, and/or Edge installed. Downloading mods will fail otherwise. Prioritizes using Chrome > Firefox > Edge.
Note: Explicit mods that require signing in cannot be downloaded.

Additionally, we write mod files to folders within the current working directory, but the mod manager handles moving/deleting files and folders because we supply it with the file paths.
Though unlikely, if GameBanana ever significantly revamps the way they display mods on their page (namely the html class names of the download buttons or the urls of the mod pages), this code will likely need an update.
'''

class DisplayedElementInListLocated(Protocol):
    '''
    A custom function to be called by WebDriverWait.until() repeatedly, until one of the selenium locators detects a displayed element on the page.
    Primarily used for finding either a download link or the nsfw content proceed button (in the case where download links may be absent).
    Returns the first element detected from the locators, or False if no element could be found with any of the locators.
    '''
    def __init__(self, locators: list[tuple[By, str]]):
        self.locators = locators
        
    def __call__(self, driver):
        for by, value in self.locators:
            try:
                element = driver.find_element(by, value)
                if element.is_displayed():
                    return element
            except:
                continue
        return False
    
def _find_browser() -> str:
    '''
    Attempts to locate edge, firefox, or chrome on the system, in that order.
    Returns the first browser name found.
    Returns an empty string if nothing could be found.
    '''
    if WINREG_IMPORTED: #method for windows
        for name, path_list in WINDOWS_BROWSER_REGISTRY_PATHS.items():
            for path in path_list:
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as key:
                        winreg.QueryValueEx(key, "") #gives an error if it doesn't succeed
                        return name
                except: #this will occur on linux all the time, or on windows if the application isn't found
                    continue
    else: #method for linux and macOS
        for name, path in BROWSER_PATHS.items():
            if path:
                return name
    return ""

def _download_mod_from_page(file_url_link: str, mod_name: str, downloaded_file_paths: list[str], target_directory: str, cs: cloudscraper.CloudScraper) -> bool:
    '''
    Downloads the file at href via a GET request, and writes it to /target_directory/mod_name.
    Only use this when you have the exact address of the hosted file. Use download_mods() if you only have the mod page.
    Appends the newly downloaded file's path to downloaded_file_paths.
    Returns True if the request and download were successful, False if not.
    '''
    try:
        response = cs.get(file_url_link, stream=True, allow_redirects=True, timeout=RESPONSE_WAIT_TIME)
        file_path = os.path.join(target_directory, mod_name)
        with open(file_path, "wb") as file:
            for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                file.write(chunk)
        downloaded_file_paths.append(os.path.abspath(file_path))
        return True
    except Exception as e:
        print("Error with downloading mod: " + str(e))
        return False

def download_mods(mod_page_url: str, cs: cloudscraper.CloudScraper, mod_index: int=-1) -> tuple[list[str], bool]:
    '''
    mod_page_url should be the actual mod's page, like "https://gamebanana.com/sounds/79236".
    Opens a webdriver and downloads all the mods (if no index is given/mod_index is -1) or a singular mod for mods with alternate versions (if an index is given) from the page.
    Does not allow downloading archived (outdated) mods. Cannot download mods with adult content that requires signing in, but does allow downloading mild nsfw warning mods.
    The webdriver can only execute chrome, firefox, or edge. Anything else on the system will not download anything. Does not download anything if mod_index >= the amount of non-archived mods on the page.
    Downloads the mod(s) to /DOWNLOAD_FOLDER/TEMPORARY_FOLDER_PREFIX[Download Number] (moving/removing them is taken care of elsewhere by the mod manager).
    Returns a tuple, containing a list of absolute paths on the local device to all mods successfully downloaded, 
    and a bool corresponding to if all requested mods were downloaded successfully (returns False if at least one failed to download, or if an error prevented downloading altogether).
    '''
    downloaded_file_paths = [] #this will be returned later, propagated with file paths on the local device
 
    #first we need to check the browsers on the system to see if any are usable for downloading mods
    browser_name = _find_browser()
    user_data_dir = None
    print("Using browser: " + browser_name)
    match browser_name:
        #IMPORTANT: options.set_capability("pageLoadStrategy", "eager") is the most important to set by far, reduces the total duration of this function to seconds instead of minutes
        # setting the user agent is also important
        case "chrome":
            options = ChromeOptions()
            options.add_argument("--log-level=3")
            options.add_argument("--disable-logging")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-gpu")
            options.add_argument("--disable-extensions")
            options.add_argument("--disable-popup-blocking")
            options.add_argument("--no-sandbox")
            options.add_argument("--enable-unsafe-swiftshader")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--headless")
            options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            options.set_capability("pageLoadStrategy", "eager")
            user_data_dir = tempfile.mkdtemp() #this should fix the user data directory already in use bug
            options.add_argument(f'--user-data-dir={user_data_dir}')
            driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)

        case "firefox":
            #firefox opens up dialog when downloading by default, which gives us errors unless we create a profile with custom settings
            profile = webdriver.FirefoxProfile()
            profile.set_preference("browser.download.folderList", 2) #2 is for downloading to custom folders
            profile.set_preference("browser.download.dir", os.getcwd()) #downloads to the current working directory
            profile.set_preference("browser.helperApps.neverAsk.saveToDisk", "application/zip,application/rar,application/7z") #specify the supported file types
            profile.set_preference("browser.download.manager.showWhenStarting", False) #gets rid of dialog

            options = FirefoxOptions()
            options.profile = profile
            options.add_argument("--width=1920")
            options.add_argument("--height=1080")
            options.add_argument("--headless")
            options.set_capability("pageLoadStrategy", "eager")

            service = FirefoxService(GeckoDriverManager().install()) 
            driver = webdriver.Firefox(service=service, options=options)

        case "edge":
            options = EdgeOptions()
            options.add_argument("--disable-gpu")
            options.add_argument("--disable-extensions")
            options.add_argument("--disable-popup-blocking")
            options.add_argument("--no-sandbox")
            options.add_argument("--enable-unsafe-swiftshader")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--headless")
            options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            options.set_capability("pageLoadStrategy", "eager")
            driver = webdriver.Edge(service=EdgeService(), options=options)

        case _:
            return [], False

    mods_downloaded_successfully = True #set this to False when a mod fails to download

    try:
        #first retrieve the actual mod's page, then find the (not fake) download buttons
        start_time = time.time()
        driver.get(mod_page_url)
        print("Loaded page: " + mod_page_url)
        required_element = None #download or proceed button
        try:
            #we have to wait until a download link or a 'Proceed' button is found(some mod pages do not have downloads or contain explicit mods)
            required_element = WebDriverWait(driver, PAGE_LOADING_WAIT_TIME).until(DisplayedElementInListLocated([(By.CSS_SELECTOR, DOWNLOAD_LINK_CSS_SELECTOR),(By.CSS_SELECTOR, NSFW_CONTENT_BUTTON_CSS_SELECTOR)]))
        except TimeoutException as e:
            print("Error, could not find a download link: " + str(e))
            driver.quit()
            try:
                if user_data_dir:
                    shutil.rmtree(user_data_dir)
            except:
                print("Could not remove temporary profile folder.")
            return [], False
        
        if not required_element: #no download button or proceed button on the page
            try:
                if user_data_dir:
                    shutil.rmtree(user_data_dir)
            except:
                print("Could not remove temporary profile folder.")
            return [], False
        
        if required_element.tag_name.lower() == "button": #if there is mild nsfw content then we will have a 'Proceed' button (explicit nsfw content will never be downloaded, however)
            #we need an additional step here to click on the button, and then wait again until we find a download link
            try:
                driver.execute_script("arguments[0].scrollIntoView();", required_element)      
                WebDriverWait(driver, PAGE_LOADING_WAIT_TIME).until(expected_conditions.element_to_be_clickable(required_element))
                driver.execute_script(f"window.scrollTo({required_element.location['x']}, {required_element.location['y']});")
                required_element.click()
                WebDriverWait(driver, PAGE_LOADING_WAIT_TIME).until(expected_conditions.presence_of_element_located((By.CSS_SELECTOR, DOWNLOAD_LINK_CSS_SELECTOR)))
            except TimeoutException as e:
                print("Error, could not find a download link: " + str(e))
                driver.quit()
                try:
                    if user_data_dir:
                        shutil.rmtree(user_data_dir)
                except:
                    print("Could not remove temporary profile folder.")
                return [], False
        
        download_page_link = driver.find_element(By.CSS_SELECTOR, DOWNLOAD_LINK_CSS_SELECTOR) #all of the real downloads (because of ads) have this selector, but it redirects to different (but similar) page
        actual_download_page_url = download_page_link.get_attribute("href")
        '''
        We need to do this because from the main mod page we will get redirected to something like 'https://gamebanana.com/sounds/download/79236#FileInfo_1403876' after clicking a download button.
        This sends us to a page with all the actual download links, it is due to multiple downloads/version of the same mod existing. The first link contains the downloads for the other mod versions, so this is fine.
        '''
        if actual_download_page_url: #we found at least one download link
            driver.get(actual_download_page_url)

            #need the download buttons to load first
            try:
                WebDriverWait(driver, PAGE_LOADING_WAIT_TIME).until(expected_conditions.presence_of_all_elements_located((By.CSS_SELECTOR, DOWNLOAD_LINK_CSS_SELECTOR))) #wait a download link to load before requesting
            except TimeoutException as e:
                print("Error, could not locate download buttons: " + str(e))
                driver.quit()
                try:
                    if user_data_dir:
                        shutil.rmtree(user_data_dir)
                except:
                    print("Could not remove temporary profile folder.")
                return [], False
                
            css_file_list = driver.find_element(By.CSS_SELECTOR, UP_TO_DATE_MOD_LIST_CSS_SELECTOR) #these are all the non-outdated files
            mod_download_links = css_file_list.find_elements(By.CSS_SELECTOR, DOWNLOAD_PAGE_MOD_LINKS_CSS_SELECTOR)
            mod_names = css_file_list.find_elements(By.CSS_SELECTOR, DOWNLOAD_PAGE_MOD_NAMES_CSS_SELECTOR)

            #only do this because the tempfile module wasn't playing nice with multithreading, the mod browser handles file and folder deletion
            directory_number = 0
            while (os.path.exists(os.path.join(DOWNLOAD_FOLDER, TEMPORARY_FOLDER_PREFIX + str(directory_number)))):
                directory_number += 1
            temp_directory = os.path.join(DOWNLOAD_FOLDER, TEMPORARY_FOLDER_PREFIX + str(directory_number))
            try:
                os.makedirs(temp_directory, exist_ok=True)
            except OSError as e:
                print("Error, could not create temporary directory: " + str(e))
                driver.quit()
                try:
                    if user_data_dir:
                        shutil.rmtree(user_data_dir)
                except:
                    print("Could not remove temporary profile folder.")
                return [], False

            if mod_index >= 0: #download a singular mod (if the index exists)
                if mod_index >= len(mod_download_links): #mod index not found
                    shutil.rmtree(temp_directory)
                    print("Error, mod index does not exist on page")
                    driver.quit()
                    try:
                        if user_data_dir:
                            shutil.rmtree(user_data_dir)
                    except:
                        print("Could not remove temporary profile folder.")
                    return [], True
                
                file_url = mod_download_links[mod_index].get_attribute("href")
                mod_name = mod_names[mod_index].text
                if _download_mod_from_page(file_url, mod_name, downloaded_file_paths, temp_directory, cs):
                    print("Downloaded mod successfully: " + mod_name)
                else:
                    mods_downloaded_successfully = False
                    print("Failed to download mod: " + mod_name)

            else: #download every mod on the page
                for i in range(len(mod_download_links)):
                    file_url = mod_download_links[i].get_attribute("href")
                    mod_name = mod_names[i].text
                    if _download_mod_from_page(file_url, mod_name, downloaded_file_paths, temp_directory, cs):
                        print("Downloaded mod successfully: " + mod_name)
                    else:
                        mods_downloaded_successfully = False
                        print("Failed to download mod: " + mod_name)

        for file_path in downloaded_file_paths:
            print("Downloaded mod file path at: " + file_path)

    except Exception as e:
        print("Error with downloading from webdriver: " + str(e))

    finally:
        end_time = time.time()
        print(f"Total elapsed time: {end_time - start_time} seconds")
        driver.quit()
        try:
            if user_data_dir:
                shutil.rmtree(user_data_dir)
        except:
            print("Could not remove temporary profile folder.")
        return downloaded_file_paths, mods_downloaded_successfully

#run as standalone for testing
if __name__ == "__main__":
    scraper = cloudscraper.create_scraper()
    download_page = "https://gamebanana.com/sounds/79236" #sound file, multiple alternate file options
    #download_page = "https://gamebanana.com/mods/621072" #has multiple archived files
    #download_page = "https://gamebanana.com/mods/619503" #contains nsfw
    download_mods(download_page, scraper, 0)