These are Python scripts that allow you to extract assets from Frostbite Engine games.
They're based off Frankelstner's scripts, I've updated them to Python 3 and did a bunch of tweaks and cleanups to them.

**All scripts require Python 3 (64-bit)!**

There is one folder for each Frostbite version:
 * frostbite2 
   * Frostbite Engine 2 (2011-2012) - Battlefield 3, Need for Speed: The Run, ...
 * frostbite3
   * Frostbite Engine 3 (2013-present) - Battlefield 4, Need for Speed: Rivals, ...
   * Newest games from 2018 and later (Battlefield V, FIFA 19, Anthem) are not supported yet.
   * Mass Effect: Andromeda is not supported yet since its TOC files are encrypted.
   * IMPORTANT: FIFA 18 uses Oodle compression but I can't distribute the library required to decompress it here since it's proprietary. So make sure you grab oo2core_4_win64.dll from your game installation and place it into frostbite3 directory before extraction.
 
In each directory, you'll find the following scripts:
 * dumper - adjust the paths at the start and run it to dump all the contents of superbundles; all the other scripts are meant to be used with the resulting dump
 * ebxtotext - converts EBX files to plain text TXT; useful if you want to view the game's scripts, etc
 * ebxtoasset - runs through EBX files and uses known EBX types to extract assets from chunks, the resulting file takes the EBX name; currently, only sounds and movies are supported
 
To eleborate on Frostbite asset structure, all data is contained inside superbundles (SB files). Each superbundle contains bundles and each bundle, in turn, contains the following file types:
 * ebx - these are so called asset nodes; this format is the cornerstone of Frostbite, they're used to reference the actual game assets stored inside res and chunk files as well as store game scripts, configurations, etc
 * res - these contain assets like meshes, animations, shaders, texture headers, sometimes movies
 * chunk - these contain assets like textures, movies, sounds, etc

Additionally, superbundle itself can also contain chunks.
 
So if you want to get the game assets you need to take the EBX files and use them to find your data inside the chunks. This is what ebxtoasset script does for you. Frostbite has many different EBX asset types, here are the most relevant ones:
 * SoundWaveAsset - general sound asset, references chunks containing SPS files (standard EA audio format they've been using since 2010)
 * NewWaveAsset, LocalizedWaveAsset - new sound asset types introduced in 2017, same as SoundWaveAsset but simplified
 * TextureAsset - references texture header (ITexture) RES file which lists chunks containing raw image data for each mipmap level
 * SkinnedMeshAsset, RigidMeshAsset, CompositeMeshAsset, ... - references mesh set header (MeshSet) RES file which lists chunks containing meshes for each LOD

CREDITS:
 * Frankelstner - initial research of Frostbite formats and original Python scripts
 * NoFaTe - some improvements to Ebx and DbObject parser
 
Libraries used:
 * LZ4 - https://github.com/lz4/lz4
 * Zstd - https://github.com/facebook/zstd
 * Oodle - http://www.radgametools.com/oodle.htm
