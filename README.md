These are Python scripts that allow you to extract assets from Frostbite Engine games.
They're based off Frankelstner's scripts, I've updated them to Python 3 and did a bunch of tweaks and cleanups to them.

**All scripts require Python 3 (64-bit)!**

There is one folder for each Frostbite version:
 * frostbite2 
   * Frostbite Engine 2 (2011-2012) - Battlefield 3, Need for Speed: The Run, ...
 * frostbite3
   * Frostbite Engine 3 (2013-present) - Battlefield 4, Need for Speed: Rivals, ...
   * Newest games from 2018 and later (Star Wars: Battlefront II, Battlefield V, FIFA 19, Anthem) are not supported yet.
   
IMPORTANT! Some games require proprietary libraries that I can't distribute here. You'll need to get them youself if you want to extract those games:
 * Some X360 games use X360 compression on some SB files. Find Xbox 360 File Decompression Tool (xbdecompress.exe) and put it into thirdparty directory.
 * FIFA 18 uses Oodle compression. Grab oo2core_4_win64.dll from your game installation and put it into thirdparty directory.

In each directory, you'll find the following scripts:
 * dumper - adjust the paths at the start and run it to dump all the contents of superbundles; all the other scripts are meant to be used with the resulting dump
 * ebxtotext - converts EBX files to plain text TXT; useful if you want to view the game's scripts, etc
 * ebxtoasset - runs through EBX files and uses known EBX types to extract assets from chunks, the resulting file takes the EBX name; currently, only sounds and movies are supported

To eleborate on Frostbite asset structure, all data is contained inside superbundles (SB files). Each superbundle contains bundles and each bundle, in turn, contains the following file types:
 * ebx - these are so called asset nodes; this format is the cornerstone of Frostbite, they're used to reference the actual game assets stored inside res and chunk files as well as store game scripts, configurations, etc
 * res - these contain assets like mesh headers, animations, shaders, texture headers, sometimes movies
 * chunk - these contain assets like meshes, textures, movies, sounds, etc

Additionally, superbundle itself can also contain chunks.

So if you want to get the game assets you need to take the EBX files and use them to find your data inside the chunks. This is what ebxtoasset script does for you. Frostbite has many different EBX asset types, here are the most relevant ones:
 * SoundWaveAsset - general sound asset, references chunks containing SPS files (standard EA audio format they've been using since 2010)
 * NewWaveAsset, LocalizedWaveAsset - new sound asset types introduced in 2017, similar to SoundWaveAsset but all data about variations and segments is stored in NewWaveResource RES file
 * TextureAsset - references texture header (DxTexture, Texture, ...) RES file which references chunk containing raw image data for each mipmap level
 * SkinnedMeshAsset, RigidMeshAsset, CompositeMeshAsset, ... - references mesh set header (MeshSet) RES file which lists chunks containing meshes for each LOD

CREDITS:
 * Frankelstner - initial research of Frostbite formats and original Python scripts
 * NoFaTe - some improvements to Ebx and DbObject parser

Libraries used:
 * LZ4 - https://github.com/lz4/lz4
 * Zstd - https://github.com/facebook/zstd
 * Oodle - http://www.radgametools.com/oodle.htm
