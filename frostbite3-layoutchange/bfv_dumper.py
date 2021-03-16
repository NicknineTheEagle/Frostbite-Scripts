# coding=utf-8
 
"""
 
    This script runs through all toc files it can find and uses that information to extract the files to a target directory.
    Often the assets are actually stored in cascat archives (the sbtoc knows where to search in the cascat), which is taken care of too.
    The script does not overwrite existing files (mainly because 10 sbtocs pointing at the same asset in the cascat would make the extraction time unbearable).
 
    *Note: About the terms "Patched" and "UNPatched".  UNPatched refers to the files normally in the Data and xpack folders.
    "Patched" refers to the files found in the Patch folder.
 
    If you REALLLLYYY wanna know why. See below:
    (I wasn't the one who decided to refer to this as that or files you download from a patch as UNpatched...I just made sense of it)
    It can get confusing because at a glance it will seem like the files from the Update folder(the "Patched") are small amounts of data that are being applied to the
    files in the Data/Xpack folders(the "UNpatched") and patching them.
    In many cases the "Patched" files contain only the CHANGES to a file(and info about what bytes to change) and not a whole file.
    The changes are then pieced together with the "UNpatched" files ...you know kinda like a patch being applied to a file.
    "UNpatched" files are UNpatched because they are the "source data" the "original" data...un-patched data. Then some frostbite black magic happens and
    a few bytes are cut out of the "UNpatched" data and a few bytes cut out of the "Patched" data. A little bit of ducktape, glue and luck and you get a nice, shiny,
    updated weapon or do-hickey...hopefully.
    
    [11/11/2018]
    Updated to be able to read the new manifest layout system used in StarWars Battlefront II and Battlefield V by GalaxyMan2015
 
 
"""
 
import cas
# import noncas
import os
# import binascii
from binascii import hexlify
# from binascii import unhexlify
from struct import pack, unpack
# from cStringIO import StringIO
from ctypes import *
# import cPickle
import glob
 
 
# do yourself a favor and don't dump into the Users folder (or it might complain about permission)
bf1Directory = r"G:\Origin Games\Battlefield V"
targetDirectory = r"G:\BFV"
 
# What kinda of files do you want to extract.
# If you just want data, stats, files to convert to text files and read. Only enable EBX dumping. This DRAMATICALLY reduces the amount of time extraction takes.
# If you want textures, audio, etc etc turn everything to True(res files won't give you a texture or anything without it's corresponding Chunk file).
 
dumpEbxEnabled = False  # DATA
# EVERYTHING ELSE ←↓
dumpResEnabled = True
dumpChunksEnabled = False
dumpChunksTocEnabled = False
 
debug = False
# save the output/console log to a file (dumper.log)
# TODO: output log file
# outputLog = False
# Prints every file that didn't error while dumping in the console
outputPrint = True
 
# The following paths do not require adjustments (unless the devs decided to rename their folders). Note that they are relative to "bf1Directory".
 
# As files are not overwritten, the patched files need to be extracted first.
# The script will dump all tocs it can find in these folders+sub folders:
tocRootPatched = r"Patch"  # patched FIRST
tocRootXpack = r"Update"  # then and xpack files
tocRootUnPatched = r"Data"  # unpatched vanilla files LAST
 
# Note: The "Patch" tocRoot contains both patch (for vanilla AND xpack) and unpatched xpack files. The reason it still
#      works correctly is because it goes through the folders alphabetically, so the patch comes first.
# About the names of the res files:
#   The first part after the actual name (but before the file extension) is the RID. It's used by ebx to import res files.
#   When it is not just nulls, the resMeta is added after the RID. Its purpose depends on the file type.
 
#LZ77 = cdll.LoadLibrary("LZ77")
ZSTD = cdll.LoadLibrary("ZSTD")
 
# File extensions given to Res files.
# Most are derived from hash(FNV-1) of the last 16 bytes of a res files iirc. Haven't actually checked in a long while,
#  last time the dict was updated noFate provided the missing res file extensions so I haven't actually looked at the hashes in years.
# Originally(BF3) Frankelstner just made up/made guessed at file extensions before the names were figured out.
# Others followed suit and used extensions that were convenient while developing tools to work with the res files.
# Some res tools may not get along with the real file extensions,
# you can just change the name of it in the resTypes dict so it will work with the tools you use.
resTypes = {
    0xEFC70728: "ZoneStreamerData", # New BF1 Res Asset. Seems to be more of a controling of resourses for loading levels on the fly then a res itself
    0x86521D6C: ".LMS", # New BF1 "LinearMediaRuntimeResource" Seems to only be used for cinematic SP stuff, maybe mp zep crash
    0x91043F65: ".HavokPhysicsData",
    0x4864737B: ".HavokDestructionPhysicsData",
    0x319D8CD0: ".RagdollResource",
    0x6BB6D7D2: ".Terrain",
    0x22FE8AC8: ".TerrainStreamingTree",
    0x51A3C853: ".AssetBank",
    0x3568E2B7: ".RawFileData",
    0xD070EED1: ".AnimationTrackData",
    0x49B156D4: ".Mesh",  # .MestSet IS WHAT MANY MESH TOOLS USE
    0x2D47A5FF: ".SwfMovie",  # .swf
    0x36F3F2C0: ".IShaderDatabase",
    0xE565EB15: ".DxShaderDatabase",
    0x10F0E5A1: ".DxShaderProgramDatabase",  # BF4 res
    0xF04F0C81: ".Dx11ShaderProgramDatabase",
    0x5C4954A6: ".DxTexture",  # BF4 res
    0xC417BBD3: ".ITexture",  # BF4 res
    0x1CA38E06: ".VisualTerrain",
    0x15E1F32E: ".TerrainDecals",  # BF4 res
    0x9C4FAA17: ".HeightFieldDecal",
    0x41D57E10: ".RenderTexture",
    0x30B4A553: ".OccluderMesh",
    0x70C5CB3E: ".EnlightenDatabase",
    0x59CEEB57: ".EnlightenShaderDatabase",
    0x5BDFDEFE: ".EnlightenSystem",
    0xE156AF73: ".EnlightenProbeSet",
    0x7AEFC446: ".StaticEnlightenDatabase",
    0xC6DBEE07: ".AnimatedPointCloud",
    0xC78B9D9D: ".ImpulseResponse",
    0xafecb022: ".Luac",
    0x957C32B1: ".AtlasTexture",
    0xC6CD3286: ".EnlightenStaticDatabase",
    0xA23E75DB: ".TerrainLayerCombinations",
    0xE36F0D59: ".HavokClothPhysicsData",
    # IIRC THIS IS WHAT THE "ITEXTURE FILES RES TYPE IS. THIS IS WHERE YOU CAN DECIDE WHAT FILE EXTENSION YOU WANT IT TO BE, EASIER TO DO IT NOW THEN BATCH RENAME EVERYTHING LATER
    0x6BDE20BA: ".Texture",
    0x9D00966A:".UITtfFontFile",
    0x9D00966A: ".TTF",
    0xC611F34A: ".MeshEmitterResource",
    0x0DEAFE10: ".IES",  # Illumination Engineering Society, light profiles. google it
    #0x387CA0AD: '.BNRY'  # MAYBE. bnry is a type of res(texture?) found in The Sims apparently
    
    # other resource types
    0x8D9E6F01: ".PcaComponentWeightsResource",
    0x85AC783D: ".EAClothAssetData",
    0xBA02FEE0: ".MeshAdjancencyResource",
    0x1091C8C5: ".MorphTargetsResource",
    0x85EA8656: ".EAClothEntityData",
    0x59C79990: ".FaceFxResource",
    0xAD1AC4FD: ".LargeParticleCloud",
    0xEB228507: ".MorphResource",
    0x52EE0D39: ".PlayerPresetResource",
    0xAFECB022: ".CompiledLuaResource",
    0x5E862E05: ".LocalizedStringResource",
    0xCB8BCD07: ".GtsoLut",
    0x387CA0AD: ".EAClothData",
    0xC664A660: ".PamReplayResource",
    0x76742DC8: ".DelayLoadBundleResource",
    0x24A019CC: ".MorphMaterialResource",
    0x428EC9D4: ".BundleRefTableResource",
    0xEF23407C: ".FifaPhysicsResourceData",
    0xB2C465F6: ".NewWaveResource",
    0xB15AD3FD: ".EnlightenShaderDatabaseResource",
    0x89983F10: ".SvgImage",
    0x6B4B6E85: ".Dx12PcRvmDatabase",
    0x50E8E7EE: ".Dx12NvRvmDatabase",
    0xF7CC814D: ".Dx11NvRvmDatabase",
    0x8DA16895: ".Dx11RvmDatabase",
    0x7DD4CC89: ".SerializedExpressionNodeGraph",
    0x4B803D3B: ".PathfindingRuntimeResource",
    0x1445F2DB: ".AtlasGroupResource",
    0x78791C75: ".EmitterGraphResource",
    0x41759364: ".PhysicsResource",
    0x00D41D60: ".RaceGroundTextureResource",
    0x39173AB8: ".MetaMorphTargetMeshResourceAsset",
    0x59BBF1E8: ".FootballMetaMorphVertexRegionWeightsResource",
    0x4C4D624A: ".FootballMetaMorphMeshDeltaPositionsResource",
    0x3B9D1688: ".PSDResource",
    0x85548684: ".CompressedClipData",
    0xEC1B7BF4: ".AntResource"
}
 
 
# noinspection PyPep8Naming
def pp(strD, f_err):
    """
 
    :param strD: output s
    :param f_err: 0 = false 1 = true 3 = debug
    """
    if outputPrint or f_err or f_err == 3:
        if f_err != 3:
            print strD
        else:
            if debug:
                print strD
 
 
def hex2(num):
    """
 
    :param num:
    :return: e.g. 10 => '0000000a'
    """
    return hexlify(pack(">I", num))
 
 
# noinspection PyClassHasNoInit,PyRedundantParentheses
class Stub():
    """
        generic struct to assist creating a dictionary of SHA and information from each cat entry
 
    :entry.offset:
    :entry.size:
    :ProcSize: Can't remember what this is anymore
    :casNum:
    """
    pass
 
 
# noinspection PyPep8Naming,PyShadowingNames
def readCat(catDict, catPath):
    """
    Take a dict and fill it using a catData file: sha1 vs (offset, size, ProcSize, casNum)
 
    :param catDict:
    :param catPath:
    """
    
    if not os.path.exists(catPath):
        return
    
    catData = cas.unXor(catPath)
    Nyan = 0x28  # Nyan plus entrties count
    catData.seek(16)  # skip nyan
    EntryCountA, EntryCountB = unpack("<II", catData.read(8))
    casDirectory = os.path.dirname(catPath) + "\\"  # get the full path so every entry knows whether it's from the patched or unpatched catData
    catData.seek(Nyan + (EntryCountA * 36))
    current_entry = 0
    while current_entry < EntryCountB:
        deltaEntry = Stub()
        sha1 = catData.read(20)
        deltaEntry.baseSha1 = catData.read(20)
        deltaEntry.deltaSha1 = catData.read(20)
        catDict[sha1] = deltaEntry
        current_entry += 1
    current_entry = 0
    catData.seek(Nyan)
    while current_entry < EntryCountA:
        entry = Stub()
        sha1 = catData.read(20)
        entry.offset, entry.size, ProcSize, casNum = unpack("<IIII", catData.read(16))
        entry.path = casDirectory + "cas_" + ("0" + str(casNum) if casNum < 10 else str(casNum)) + ".cas"
        catDict[sha1] = entry
        current_entry += 1
 
 
# noinspection PyUnusedLocal,PyUnusedLocal,PyUnusedLocal,PyPep8Naming
def dump(tocPath, targetFolder):
    """
    Take the filename of a toc and dump all files to the targetFolder.
 
    # Depending on how you look at it, there can be up to 2*(3*3+1)=20 different cases:
    #    The toc has a cas flag which means all assets are stored in the cas archives. => 2 options
    #        Each bundle has either a delta or base flag, or no flag at all. => 3 options
    #            Each file in the bundle is one of three types: ebx/res/chunks => 3 options
    #        The toc itself contains chunks. => 1 option
    #
    # Simplify things by ignoring base bundles (they just state that the unpatched bundle is used),
    # which is alright, as the user needs to dump the unpatched files anyway.
    #
    # Additionally, add some common fields to the ebx/res/chunks entries so they can be treated the same.
    # => 6 cases.
 
 
    :param tocPath:
    :param targetFolder:
    :return:
    """
    toc = cas.readToc(tocPath)
    pp(tocPath, 0)
    if not (toc.get("bundles") or toc.get("chunks")): return  # there's nothing to extract (the sb might not even exist)
 
    sbPath = tocPath[:-3] + "sb"
    sb = open(sbPath, "rb")
 
    for tocEntry in toc.bundles:
        if tocEntry.get("base"): continue
        sb.seek(tocEntry.offset)
 
        # read the bundle and wish there were cas flags
        if toc.get("cas"):  # so far all ebx and res are cas
            bundle = cas.Entry(sb)
 
            # make empty lists for every type to make it behave the same way as noncas
            # for listType in ("ebx","res","chunks","dbx"):#Added DBX - look into DBX, maybe something changed and can account for missing data?
            # scratch that DBX is decompiled EBX, may not be in client file what so ever?
            for listType in ("ebx", "res", "chunks"):
                if listType not in vars(bundle):
                    vars(bundle)[listType] = []
 
            # The noncas chunks already have originalSize calculated in Bundle.py (it was necessary to seek through the entries).
            # Calculate it for the cas chunks too. From here on, both cas and noncas ebx/res/chunks (within bundles) have size and originalSize.
            if bundle.chunks is None:
                pp("no chunks in bundle: %s: %s " % (sbPath, bundle.path), 3)
            else:
                for chunk in bundle.chunks:
                    chunk.originalSize = chunk.logicalOffset + chunk.logicalSize
 
            # So yeah, no real flags anywhere for patch type. Instead just break it down into patch, xpack, data and manually define unpack methods
            # pick the right function
            if "Patch" in sbPath:
                subroot = "Patch"
                writePayload = casPatchedPayload
                sourcePath = None  # the noncas writing function requires a third argument, while the cas one does not. Hence make a dummy variable.
            else:
                if "Update" in sbPath:
                    subroot = "Update"
                    writePayload = casUpdatePayload  # created new payload type to deal with new folder and lack of flags
                    sourcePath = None
                else:
                    subroot = "Data"
                    writePayload = casPayload
                    sourcePath = None
        else:
            print "The toc file path %s does not match any tocRoots [ %s , %s, %s]" % (sbPath, tocRootPatched, tocRootXpack, tocRootUnPatched)
            raise Exception("The toc file path %s does not match any tocRoots [ %s , %s, %s]" % (sbPath, tocRootPatched, tocRootXpack, tocRootUnPatched))
            # exit()
            # asdf()
            # element ghetto stop™ patent pending
 
        # pick a good filename, make sure the file does not exist yet, create folders, call the right function to write the payload
        if dumpEbxEnabled and bundle.ebx is not None:
            for entry in bundle.ebx:
                targetPath = targetFolder + "/bundles/ebx/" + entry.name + ".ebx"
                if prepareDir(targetPath): continue
                writePayload(entry, targetPath, sourcePath)
                pp("\t/%s.ebx" % entry.name, 0)
                # pp("\t"+targetPath, 0)
        else:
            pp("no ebx in bundle: %s: %s " % (sbPath, bundle.path), 3)
            print "pause"
 
        if dumpResEnabled and bundle.res is not None:
            for entry in bundle.res:  # always add resRid to the filename. Add resMeta if it's not just nulls. resType becomes file extension.
                rID = "".join(map(str.__add__, hexlify(pack(">Q", entry.resRid))[-2::-2], hexlify(pack(">Q", entry.resRid))[-1::-2]))  # fixed resId so it matches the whats in the ebx
                basePath = targetFolder + "/bundles/res/" + entry.name
                targetPath = targetFolder + "/bundles/res/" + entry.name + " " + rID
                # ignore resMeta for textures and when its null
                if entry.resType not in (2432974693, 1809719482):
                    # add resMeta so long as the doesn't make the name/path to long
                    if entry.resMeta != "\0" * 16: targetPath += " " + hexlify(entry.resMeta)
                if entry.resType not in resTypes:
                    targetPath += ".unknownres_" + hex2(entry.resType)
                else:
                    targetPath += resTypes[entry.resType]
                if prepareDir(targetPath): continue
                # if preparing the directory/file fails check if the file already exist(been dumped from another bundle.)
                # right now it goes with the first version of a res file it comes across with should be fine. (tocRoot order[ Patch > Update > Data])
                # if assets seem incorrect(partial, wrong size, corrupt) I will implement a check for things like if variations of a single asset, mipMaps and an option to dump them all anyways.
                try:
                    if len(glob.glob(basePath + "*" + resTypes[entry.resType])) == 0:
                        writePayload(entry, targetPath, sourcePath)
                        pp(targetPath, 0)
                    else:
                        pass
                except Exception as err1:
                    pp("excepted error: %s" % err1, 1)
                    # shit hit the fan for that res, lets go for it anyway.
                    writePayload(entry, targetPath, sourcePath)
                    pp(targetPath, 0)
        else:
            if dumpResEnabled and bundle.res is None:
                pp("no res in bundle: %s: %s " % (sbPath, bundle.path), 3)
 
        if dumpChunksEnabled and bundle.chunks is not None:
            # id becomes the filename. If meta is not empty, add it to filename.
            for i in xrange(len(bundle.chunks)):
                entry = bundle.chunks[i]
                targetPath = targetFolder + "/bundles/chunks/" + hexlify(entry.id) + ".chunk"  # keep the .chunk extension for legacy reasons
                # if you wanted chunk meta data in the file name uncomment the next line. Hint! you don't.
                # if bundle.chunkMeta[i].meta!="\x00": targetPath+=" firstMip"+str(unpack("B",bundle.chunkMeta[i].meta[10])[0])
                # chunkMeta is useless. The same payload may have several values for firstMips so chunkMeta contains info specific to bundles, not the file itself.
                if prepareDir(targetPath): continue
                writePayload(entry, targetPath, sourcePath)
                pp(targetPath, 0)
 
    #  After dealing with contents of the bundles in the toc deal with the chunks which are defined directly in the toc.
    #  These chunks do NOT know their originalSize.
    #  Available fields: id, offset, size
    # so apparently I replaced line
    # for i in xrange(len(toc.chunks)): #id becomes the filename. If meta is not empty, add it to filename.
    # entry=toc.chunks[i]
    if dumpChunksTocEnabled and toc.chunks is not None:
        for entry in toc.chunks:
            targetPath = targetFolder + "/chunks/" + hexlify(entry.id) + ".chunk"
            if prepareDir(targetPath): continue
            if toc.get("cas"):
                try:
                    catEntry = catData[entry.sha1]
                    LZ77.decompressUnknownOriginalSize(catEntry.path, catEntry.offset, catEntry.size, targetPath)
                    pp(targetPath, 0)
                except Exception as err2:
                    pp("excepted error: %s" % err2, 1)
                    pass # TODO check if needed
            else:
                LZ77.decompressUnknownOriginalSize(sbPath, entry.offset, entry.size, targetPath)
                pp(targetPath, 0)
    else:
        sb.close()
 
 
# noinspection PyPep8Naming
def prepareDir(targetPath):
    """
    Makes sure the dir and folders exist to dump the data into
 
    :param targetPath:
    :return:
    """
    if os.path.exists(targetPath):
        # if debug:
            # pp("\tEXIST: "+targetPath, 3)
        return True
    dirName = os.path.dirname(targetPath)
    if not os.path.exists(dirName): os.makedirs(dirName)  # make the directory for the dll
    # this will it only prints a file name on a successful write
    #  pp(targetPath, 0)
 
 
# for each bundle, the dump script selects one of these functions
# noinspection PyUnusedLocal,PyPep8Naming
def casPayload(bundleEntry, targetPath, sourcePath):  # for data toc files
    """
 
    :param bundleEntry:
    :param targetPath:
    :param sourcePath:
    """
    try:
        catEntry = catData[bundleEntry.sha1]
        LZ77.decompress(catEntry.path, catEntry.offset, catEntry.size, bundleEntry.originalSize, targetPath)
    except Exception as err3:
        pp("fail - cat not found or error reading format\n\t Error: %s" % err3, 1)
 
 
# noinspection PyPep8Naming
def noncasPayload(entry, targetPath, sourcePath):  # no noncas in SWBF yet
    """
 
    :param entry:
    :param targetPath:
    :param sourcePath:
    """
    try:
        LZ77.decompress(sourcePath, entry.offset, entry.size, entry.originalSize, targetPath)
    except Exception as err4:
        pp("Error - noncasPayload ! cat not found or error reading format\n\t Error: %s" % err4, 1)
 
 
# noinspection PyPep8Naming
def casPatchedPayload(bundleEntry, targetPath, sourcePath):
    """
 
    :param bundleEntry:
    :param targetPath:
    :param sourcePath:
    """
    try:  # try delta patch method first
        catDelta = catData[bundleEntry.sha1].deltaSha1
        catBase = catData[bundleEntry.sha1].baseSha1
        LZ77.patchCas(catData[catBase].path, catData[catBase].offset, catData[catDelta].path, catData[catDelta].offset, catData[catDelta].size, bundleEntry.originalSize, targetPath)
    except Exception as err5:
        # pp("casPatchedPayload error: %s . Trying casPayload Method" % err5, 3)
        try:
            casPayload(bundleEntry, targetPath, sourcePath)
        except Exception as err5b:
            pp("casPatchedPayload & casPayload Error: %s . failed" % err5b, 1)
 
 
# noinspection PyPep8Naming
def noncasPatchedPayload(entry, targetPath, sourcePath):  # no noncasPatched yet in SWBF
    """
    Did I remove the baseSize from the compression algorithm and why? I Can't recall or was I debugging stuff for SWBF.
    With baseSize not used in the compression it current works with BF4/BFH/and SWBF
    patchNoncas on 10/10/2016:
    LZ77.patchNoncas(sourcePath[0], entry.baseOffset,  # entry.baseSize, sourcePath[1], entry.deltaOffset, entry.deltaSize, entry.originalSize, targetPath, entry.midInstructionType, entry.midInstructionSize)
 
    :param entry:
    :param targetPath:
    :param sourcePath:
    """
    try:
        LZ77.patchNoncas(sourcePath[0], entry.baseOffset, sourcePath[1], entry.deltaOffset, entry.deltaSize, entry.originalSize, targetPath, entry.midInstructionType, entry.midInstructionSize)
    except Exception as err6:
        pp("noncasPatchedPayload Error: %s" % err6, 1)
 
 
# noinspection PyUnusedLocal,PyPep8Naming
def casUpdatePayload(bundleEntry, targetPath, sourcePath):  # xpack files. just like unpached files but with update sb SHA1 and update cat
    """
 
    :param bundleEntry:
    :param targetPath:
    :param sourcePath:
    """
    try:
        catEntry = catData[bundleEntry.sha1]  # same as caspayload method w/ xpack tocroot
        LZ77.decompress(catEntry.path, catEntry.offset, catEntry.size, bundleEntry.originalSize, targetPath)
    except Exception as err7:
        pp("casUpdatePayload Error %s" % err7, 1)
 
 
# make the paths absolute and normalize the slashes # added all the cat paths
for path in "tocRootXpack", "tocRootPatched", "tocRootUnPatched":
    if path in locals():
        locals()[path] = os.path.normpath(bf1Directory + "\\" + locals()[path])
 
# Makes sure the target dir and path is normalized, should be already be absolute and normalized
targetDirectory = os.path.normpath(targetDirectory)
 
 
# noinspection PyPep8Naming
def dumpRoot(root):
    """
 
    :param root:
    """
    for dir0, dirs, ff in os.walk(root):
        for fname in ff:
            if fname[-4:] == ".toc":
                pp(fname, 0)
                fname = dir0 + "\\" + fname
                dump(fname, targetDirectory)
 
# create an empty dict for cat entry data
catData = dict()
 
 
# noinspection PyUnusedLocal,PyPep8Naming
def processCats(root):
    """
 
    :param root:
    """
    for dir0, dirs, ff in os.walk(root):
        for fname in ff:
            if fname == "cas.cat":
                s = dir0
                catFile = dir0 + "\\" + fname
                try:
                    readCat(catData, catFile)
                except Exception as err0:
                    pp("fail - cat not found or error reading format\n Error: %s" % err0, 1)
                catMeta = catFile + " " + str(catData.__len__())
                pp(catMeta, 1)

class ManifestFileRef:
    def __init__(self,value):
        self.value=value

    def getCatalogIndex(self): return (self.value>>12)-1
    def isInPatch(self): return (self.value&0x100)!=0
    def casIndex(self): return (self.value & 0xFF)+1
    def getCatalogPath(self,catalogs):
        root=catalogs[self.getCatalogIndex()]
        if self.isInPatch():
            root=root.replace("[PATH]","Patch")
        else:
            root=root.replace("[PATH]","Data")
        return root
    def getCas(self,catalogs): return self.getCatalogPath(catalogs) + "cas_" + str(self.casIndex()).zfill(2) + ".cas"
    def getCat(self,catalogs): return self.getCatalogPath(catalogs) + "cas.cat"
    def getBaseCat(self,catalogs): return catalogs[self.getCatalogIndex()].replace("[PATH]", "Data") + "cas.cat"
    def getPatchCat(self,catalogs): return catalogs[self.getCatalogIndex()].replace("[PATH]", "Patch") + "cas.cat"

class ManifestFile:
    def __init__(self,f):
        self.fileRef=ManifestFileRef(unpack("I",f.read(4))[0])
        self.offset=unpack("I",f.read(4))[0]
        self.size=unpack("Q",f.read(8))[0]
        self.isChunk=0

class ManifestBundle:
    def __init__(self,f,manifestFiles):
        self.bundleHash=unpack("I",f.read(4))[0]
        index=unpack("I",f.read(4))[0]
        count=unpack("I",f.read(4))[0]
        self.unk=unpack("Q",f.read(8))[0]
        self.files=[]
        while count > 0:
            self.files.append(manifestFiles[index])
            index=index+1
            count=count-1

    def getBundleFile(self): return self.files[0]

class ManifestChunk:
    def __init__(self,f,manifestFiles):
        self.id=f.read(16)
        index=unpack("I",f.read(4))[0]
        self.file=manifestFiles[index]
        self.file.isChunk=1

import binascii
class BinaryBundleEntry:
    def __init__(self,f,fileType,sha1,dataOffset):
        self.sha1=sha1
        self.fileType=fileType
        if fileType==2:
            self.id=f.read(16)
            self.logicalOffset=unpack(">I",f.read(4))[0]
            self.logicalSize=unpack(">I",f.read(4))[0]
            self.origSize=self.logicalOffset + self.logicalSize
        else:
            nameOffset=unpack(">I",f.read(4))[0]
            self.origSize=unpack(">I",f.read(4))[0]
            pos=f.tell()
            f.seek(dataOffset+nameOffset)
            self.name=cas.readNullTerminatedString(f)
            f.seek(pos)

    def setResType(self,resType): self.resType=resType
    def setResMeta(self,resMeta): self.resMeta=resMeta
    def setResRid(self,resRid): self.resRid=resRid
    
    def getFileType(self):
        if self.fileType==0: return "EBX"
        elif self.fileType==1: return "RES"
        else: return "CHUNK"

    def getName(self):
        if self.fileType==2:
            return binascii.hexlify(self.id)
        else:
            return self.name

class BinaryBundle:
    def __init__(self,filename,offset):
        f=open(filename,"rb");
        f.seek(offset)
        self.dataOffset=unpack(">I",f.read(4))[0]+4
        self.magic=unpack(">I",f.read(4))[0]^0x7065636e
        totalCount=unpack(">I",f.read(4))[0]
        ebxCount=unpack(">I",f.read(4))[0]
        resCount=unpack(">I",f.read(4))[0]
        chunkCount=unpack(">I",f.read(4))[0]
        stringsOffset=unpack(">I",f.read(4))[0]-0x24
        metaOffset=unpack(">I",f.read(4))[0]-0x24
        metaSize=unpack(">I",f.read(4))[0]

        beginDataOffset=f.tell()+4+stringsOffset
        
        # read in all sha1s
        sha1=[]
        while totalCount > 0:
            sha1.append(f.read(20))
            totalCount=totalCount-1
       
        i=0
        self.ebx=[]
        while ebxCount > 0:
            self.ebx.append(BinaryBundleEntry(f,0,sha1[i],beginDataOffset))
            ebxCount=ebxCount-1
            i=i+1

        tempResCount=resCount
        self.res=[]
        while tempResCount > 0:
            be = BinaryBundleEntry(f,1,sha1[i],beginDataOffset)
            self.res.append(be)
            tempResCount=tempResCount-1
            i=i+1
            
        j=0
        tempResCount=resCount
        while tempResCount > 0:
            self.res[j].setResType(unpack(">I",f.read(4))[0])
            tempResCount=tempResCount-1
            j=j+1
            
        j=0
        tempResCount=resCount
        while tempResCount > 0:
            self.res[j].setResMeta(f.read(0x10))
            tempResCount=tempResCount-1
            j=j+1

        j=0
        tempResCount=resCount
        while tempResCount > 0:
            self.res[j].setResRid(unpack(">Q",f.read(8))[0])
            tempResCount=tempResCount-1
            j=j+1
        
        self.chunks=[]
        while chunkCount > 0:
            self.chunks.append(BinaryBundleEntry(f,2,sha1[i],beginDataOffset))
            chunkCount=chunkCount-1
            i=i+1

    def getFileEntry(self,index):
        if index < len(self.ebx):
            return self.ebx[index]
        index=index-len(self.ebx)
        if index < len(self.res):
            return self.res[index]
        index=index-len(self.res)
        return self.chunks[index]

def binaryBundlePayload(bundleEntry, targetPath, sourcePath):  # for data toc files
    """
 
    :param bundleEntry:
    :param targetPath:
    :param sourcePath:
    """
    try:
        catEntry = catData[bundleEntry.sha1]
        ZSTD.decompress(catEntry.path, catEntry.offset, catEntry.size, bundleEntry.origSize, targetPath)
    except Exception as err3:
        pp("fail - cat not found or error reading format\n\t Error: %s" % err3, 1)
        #exit(-1)

def manifestPayload(manifestFile, targetPath, sourcePath, catalogs):
    try:
        casPath = manifestFile.fileRef.getCas(catalogs)
        ZSTD.decompress(casPath, manifestFile.offset, manifestFile.size, -1, targetPath)
    except Exception as err3:
        pp("fail - cat not found or error reading format\n\t Error: %s" % err3, 1)
        #exit(-1)
        
def processManifest(root):
    """
    :param root:
    """
    catalogs=[]
    layout = cas.readToc(root + "\\Data\\layout.toc")
    manifest = layout.get("manifest")
    fileRef = ManifestFileRef(manifest.file)
    
    for installChunk in layout.installManifest.installChunks:
        catFile=root + "\\Data\\Win32\\" + installChunk.name + "\\cas.cat"
        if not(installChunk.name.startswith("installation/default")):
            catalogs.append(root + "\\[PATH]\\Win32\\" + installChunk.name + "\\")
            
    f=open(fileRef.getCas(catalogs),"rb")
    f.seek(manifest.offset)

    fileCount=unpack("I",f.read(4))[0]
    bundleCount=unpack("I",f.read(4))[0]
    chunksCount=unpack("I",f.read(4))[0]

    manifestFiles=[]
    manifestBundles=[]
    manifestChunks=[]
    
    while fileCount > 0:
        manifestFiles.append(ManifestFile(f))
        fileCount=fileCount-1

    while bundleCount > 0:
        manifestBundles.append(ManifestBundle(f,manifestFiles))
        bundleCount=bundleCount-1

    while chunksCount > 0:
        manifestChunks.append(ManifestChunk(f,manifestFiles))
        chunksCount=chunksCount-1
        
    f.close()
    for bundle in manifestBundles:       
        bundleFile=bundle.getBundleFile()
        print "Bundle: %08x" % (bundle.bundleHash)
        binBundle=BinaryBundle(bundleFile.fileRef.getCas(catalogs), bundleFile.offset)

        readCat(catData, bundleFile.fileRef.getBaseCat(catalogs))
        readCat(catData, bundleFile.fileRef.getPatchCat(catalogs))

        writePayload=binaryBundlePayload
        if dumpEbxEnabled and len(binBundle.ebx) != 0:
            print "EBX"
            for entry in binBundle.ebx:
                targetPath = targetDirectory + "/bundles/ebx/" + entry.name + ".ebx"
                if prepareDir(targetPath): continue
                writePayload(entry, targetPath, None)
                pp(" " + targetPath, 0)

        if dumpResEnabled and len(binBundle.res) != 0:
            print "RES"
            for entry in binBundle.res:			
                rID = "".join(map(str.__add__, hexlify(pack(">Q", entry.resRid))[-2::-2], hexlify(pack(">Q", entry.resRid))[-1::-2]))  # fixed resId so it matches the whats in the ebx
                basePath = targetDirectory + "/bundles/res/" + entry.name
                targetPath = targetDirectory + "/bundles/res/" + entry.name + " " + rID
                if entry.resType not in (2432974693, 1809719482):
                    if entry.resMeta != "\0" * 16: targetPath += " " + hexlify(entry.resMeta)
                if entry.resType not in resTypes:
                    targetPath += ".unknownres_" + hex2(entry.resType)
                else:
                    targetPath += resTypes[entry.resType]
                if prepareDir(targetPath): continue
                try:
                    if len(glob.glob(basePath + "*" + resTypes[entry.resType])) == 0:
                        writePayload(entry, targetPath, None)
                        pp(" " + targetPath, 0)
                    else:
                        pass
                except Exception as err1:
                    pp("excepted error: %s" % err1, 1)
                    writePayload(entry, targetPath, None)
                    pp(" " + targetPath, 0)

        if dumpChunksEnabled and len(binBundle.chunks) != 0:
            print "CHUNKS"
            for i in xrange(len(binBundle.chunks)):
                entry = binBundle.chunks[i]
                targetPath = targetDirectory + "/bundles/chunks/" + hexlify(entry.id) + ".chunk"
                if prepareDir(targetPath): continue
                writePayload(entry, targetPath, None)
                pp(" " + targetPath, 0)

    writePayload=manifestPayload
    if dumpChunksTocEnabled and len(manifestChunks) != 0:
        print "Manifest chunks"
        for entry in manifestChunks:
            targetPath = targetDirectory + "/bundles/chunks/" + hexlify(entry.id) + ".chunk"
            if prepareDir(targetPath): continue
            writePayload(entry.file, targetPath, None, catalogs)
            pp(" " + targetPath, 0)
            
    
#if "tocRootPatched" in locals(): processCats(tocRootPatched)
#if "tocRootXpack" in locals(): processCats(tocRootXpack)
#if "tocRootUnPatched" in locals(): processCats(tocRootUnPatched)
#if "tocRootPatched" in locals(): dumpRoot(tocRootPatched)
#if "tocRootXpack" in locals(): dumpRoot(tocRootXpack)
#if "tocRootUnPatched" in locals(): dumpRoot(tocRootUnPatched)
# dump(r"D:\Program Files (x86)\Origin Games\STAR WARS Battlefront\Patch\Win32\weapons.toc","I:\hexing\dump")
processManifest(bf1Directory)
