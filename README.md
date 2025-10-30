# EZDeadlockModManager

A project built in PyQt that handles your mods for Deadlock all in the same place. Find and download your favourite mods, change their load order, toggle them on and off, and easily load them to your game and launch it with them installed, all in one application. Contains a built-in browser and downloader for mods hosted on GameBanana for easy streamlined access, as well as support for manually downloaded mods. Note that this was built mainly to be a fun side project and it is nothing official, but nevertheless is intended to be fully functional.

# Important Considerations and Dependencies

This project uses selenium webdrivers and requests as the main mode of fetching and downloading mods from GameBanana. Because of this, downloading mods will only work if at least one of Chrome, Firefox, or Edge is installed.

Chrome: https://www.google.com/intl/en/chrome/

Firefox: https://www.firefox.com/

Edge: https://www.microsoft.com/en-us/edge/download

Any .rar files will require an unrar tool to open them and extract any mods inside (it is automatically done, but requires one to be installed). The most consistent one is unRAR,
which comes as a part of winRAR: https://www.win-rar.com/ (it's free). .zip, .7z, and raw .vpk files should be fine without any additional dependencies.

This application should be compatible with both Windows and Linux.

# To build it yourself

In order to build the executable, you will need python and some dependencies for the application. It is packaged with PyInstaller, and should be just over ~50MB.
```
cd path/to/EZDeadlockModManager/
pip install -r requirements.txt
pyinstaller EZDeadlockModManager.py --icon="./resources/icon.ico" --add-data=resources:resources --distpath . --onefile --noconsole 
```
After this your executable should lie in the /EZDeadlockModManager/ directory.

# Special Thanks

Thanks to Valve for making the game, and to GameBanana and all its users for sharing all these mods. Thanks to Google for the font (Roboto).

# DISCLAIMER
This project is not affiliated with Valve or Deadlock, which is owned by Valve: https://www.valvesoftware.com/en/

nor the website Gamebanana: https://gamebanana.com/

nor the project Deadlock Mod Manager: https://deadlockmods.app/.