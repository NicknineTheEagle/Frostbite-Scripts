These are Python scripts that allow you to extract assets from Frostbite Engine games. All scripts require Python 3.
They're based off Frankelstner's scripts, I've updated them to Python 3 and did a bunch of tweaks and cleanups to them.

There is one folder for each Frostbite version:
 * frostbite2 
   * Frostbite Engine 2 (2011-2012) - Battlefield 3, Need for Speed: The Run, ...
 * frostbite3
   * Frostbite Engine 3 (2013-present) - Battlefield 4, Need for Speed: Rivals, ...
   * Newest games from 2018 (Battlefield V, FIFA 19) are not supported yet.
   * IMPORTANT: In FIFA 18, some files are compressed with Oodle. I can't distribute the library required to decompress it here since it's proprietary and the one from FIFA 18 itself is 64-bit so it can't be used with Python 32-bit. You'll need to get oo2core_6_win32.dll from a game using Oodle and put it into frostbite3 directory. Your best bet is to get it from Warframe, it's a F2P game: https://store.steampowered.com/app/230410
 
In each directory, you'll find the following scripts:
 * dumper - adjust the paths at the start and run it to dump all the contents of superbundles; all the other scripts are meant to be used with the resulting dump
 * ebxtotext - converts EBX files to plain text TXT; useful if you want to view the game's scripts, etc
 * ebxtoasset - runs through EBX files and uses known EBX types to extract assets from chunks, the resulting file takes the EBX node name; currently, only sounds and movies are supported
 
To eleborate on Frostbite asset structure, all data is contained inside superbundles (SB files). Each superbundle contains bundles and each bundle, in turn, contains the following file types:
 * ebx - these are so called asset nodes; this format is the cornerstone of Frostbite, they're used to reference the actual game assets stored inside res and chunk files as well as store game scripts, configurations, etc
 * res - these contain assets like meshes, animations, shaders, texture headers, sometimes movies
 * chunk - these contain assets like textures, movies, sounds, etc
Additionally, superbundle itself can also contain chunks.
 
So if you want to get the game assets you need to take the EBX files and use them to find your data inside the chunks. This is what ebxtoasset script does.

CREDITS:
 * Frankelstner - initial research of Frostbite formats and original Python scripts
 * NoFaTe - some improvements to Ebx and DbObject parser
