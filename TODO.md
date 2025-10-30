# TODO:
This is the list of fixes and features that need to be implemented. The tasks within each section are roughly ordered from more important to least.

🔴 High

🟡 Medium

🟢 Low

# EZDeadlockModManager.py
- [ ] 🟡 FEATURE: Add alphabetical sort for installed mods
- [ ] 🟡 FEATURE: Remove all mods/turn off mod buttons (either from addons directory or change gameinfo.gi file)
- [ ] 🟢 FEATURE: Show warning when 99+ mods enabled -> we already only add 99 mods (and display a message when doing so), so this is just extra but still useful
- [ ] 🟢 FEATURE: Add drag and drop for files straight from file explorer
- [ ] 🟢 FIX: Need to detect the other rar tools (like 7z.exe) using RAR_TOOL_REGISTRY_PATHS, and find a way on linux (setting the rar tool manually works however)
- [ ] 🟢 FIX: Add highlight for installed mod search (the search works + it scrolls to the correct item, but the highlight currently isn't visible)
- [ ] 🟢 FEATURE: Add vpk viewer/maker -> use vpk module
- [ ] 🟢 FEATURE: Add multiple profiles

# deadlock_mod_browser.py
- [ ] 🟡 FEATURE: Add sort for mods in the browser -> use the _sSort parameter, which has allowed values: new, default, updated
- [ ] 🟢 FEATURE: Add a page number
- [ ] 🟢 FIX: Sounds still play after mod browser is closed, we want to close the sound and keep the mod browser object
- [ ] 🟢 FEATURE: Cache old pages/Preload pages?

# deadlock_mod_browser_features.py
- [ ] 🟡 FIX: Make the download button's text change dynamically based on download state, requires a reference to be passed into _start_download_thread()
- [ ] 🟢 FEATURE: Blur the image preview if the visibility is set to False

# deadlock_mod_downloader

# settings_window.py
- [ ] 🔴 FEATURE: Add a way to scan for already downloaded mods -> and then rewrite modpack file (implement this to replace creation of blank modpack file upon error)
- [ ] 🟢 FEATURE: Add a way to delete old download folders if they exist, these should only exist if a user exits during a download