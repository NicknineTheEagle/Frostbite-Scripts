These are Python scripts that allow you to extract assets from Frostbite Engine games. All scripts require Python 3.
They're based off Frankelstner's scripts, I've updated them to Python 3 and did a bunch of tweaks and cleanups to them.

There is one folder for each Frostbite version:
 * frostbite2 
 ** Frostbite Engine 2 (2011-2012) - Battlefield 3, Need for Speed: The Run, ...
 * frostbite3
 ** Frostbite Engine 3 (2013-2016) - Battlefield 4, Need for Speed: Rivals, ...
 
In each directory, you'll find the following scripts:
 * dumper - djust the paths at the start to point at your game direct and run it to dump all the contents of superbundles; all other scripts are meant to be used with the resulting dump
 * ebxtotext - converts EBX files to plain text TXT; useful if you want to view the game's scripts, etc
 * ebxtoasset - runs through EBX files and uses knonwn EBX types to extract assets from chunks; currently only sounds and movies are supported
 
To eleborate on Frostbite asset structure, all data is contained inside superbundles (SB files). Each superbundle contains bundles and each bundle, in turn, contains the following file types:
 * ebx - these are so called asset nodes which are the cornerstone of Frostbite, they're used to reference the actual game assets stored inside res and chunk files as well as store game scripts, configurations, etc
 * res - these contain assets like meshes, animations, shaders, texture headers, sometimes movies
 * chunk - these contain assets like textures, movies, sounds, etc
Additionally, superbundle itself can also contain chunks.
 
So if you want to get the game assets you need to take the EBX files and use them to find your data chunks. This is what ebxtoasset script does.
