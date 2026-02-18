# Sound Modding Tutorial

<h2>Requirements</h2>

Before you begin, you need to install the Source 2 Viewer: https://s2v.app/ and install the vpk python package: https://github.com/ValvePython/vpk. You will also need Counter-Strike 2 installed on Steam to use their asset browser/compiler (Dota 2 might also work).

<h2>Important</h2>

If you want access to the uncompressed sound effect files (and sound event files, containing settings to tweak things like volume) from in game, you need to search the vpk files within /Deadlock/game/citadel/ and open them with Source 2 Viewer to find the ones you want. Once you have located them, they can be extracted with the 'Decompile and export' option. Even if you don't plan on editing the default game files, you still need to know the paths within the vpk for where your new modded files will go (e.x. /sounds/abilities/priest/priest_witching_hour_active_lp_01.vsnd_c is where Venator's ult active sound is).

Sound event files are mostly optional, but useful for changing things like volume, fade in/out, and managing multiple different sound effects for a singular character.

<h2>Instructions</h2>

1. Using Source 2 Viewer, search /Deadlock/game/citadel/ for the vpk file containing the files you want to change. Extract the sound or sound event files with 'Decompile and export' if you want to edit them. Remember the paths for the files you intend on replacing.

2. Open CSGO Workshop Tools after launching Counter Strike 2 (enable the DLC first within the settings), and create a new addon.

3. Make sure your sound files are ready (.wav or .mp3 are likely the best) and place them under /Counter Strike Global Offensive/content/csgo_addons/addon_name/sounds/.

4. .vsndevts files (sound event files, these are not compiled yet) go under /Counter Strike Global Offensive/content/csgo_addons/addon_name/soundevents/. Do not edit or remove the default soundevents_addon.vsndevts file. After compilation, these files will have the extension .vsndevts_c.

5. Double click the addon, and navigate to the asset browser once it opens. Here you have to explicitly search for all the sound and sound event files you want to compile, and double click each one to ensure that it successfully compiles.

6. Now your compiled files will be in /Counter Strike Global Offensive/game/csgo_addons/addon_name/sounds/ and
/Counter Strike Global Offensive/game/csgo_addons/addon_name/soundevents/. Create the same folder structure for the replaced files as the vpk you found them in (as seen in Source 2 Viewer) within the /input/ folder, and copy over the files you just compiled to the correct locations. Run the vpkmaker.py file, and the created mod will be titled mod.vpk.

Remember that before compilation, your sound files will be .mp3 or wav, and afterwards will be .vsnd_c. Sound event files will also go from .vsndevts to .vsndevts_c. You must use the compiled files to create the vpk.

Now you can add the newly created mod to the game via the mod manager.

<h2>Input folder structure example (Venator's ult active and blessed sound effects) </h2>

    /input

        |

        /soundevents

            |

            /hero

                |

                priest.vsndevts_c

        /sounds

            |

            /abilities

                |

                priest_witching_hour_active_lp_01.vsnd_c

                priest_witching_hour_blessed_lp_01.vsnd_c