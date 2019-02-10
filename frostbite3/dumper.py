#This script runs through all toc files it can find and uses that information to extract the files to a target directory.
#Often the assets are actually stored in cascat archives (the sbtoc knows where to search in the cascat), which is taken care of too.
#The script does not overwrite existing files (mainly because 10 sbtocs pointing at the same asset in the cascat would make the extraction time unbearable).
#Compression libs used: liblz4 (https://github.com/lz4/lz4), libzstd (https://github.com/facebook/zstd), oodle (http://www.radgametools.com/oodle.htm)
import dbo
import noncas
import ebx
import os
from struct import pack,unpack
import io
import ctypes
import zlib

#Adjust paths here.
#do yourself a favor and don't dump into the Users folder (or it might complain about permission)

gameDirectory   = r"E:\Games\EA\NFSRivals"
targetDirectory = r"E:\GameRips\NFS\NFSR\pc\dump"

#####################################
#####################################

#LZ77 = ctypes.cdll.LoadLibrary("LZ77")
liblz4 = ctypes.cdll.LoadLibrary("liblz4")
libzstd = ctypes.cdll.LoadLibrary("libzstd")
try: oodle = ctypes.windll.LoadLibrary("oo2core_6_win32")
except: oodle = None

resTypes={ #not really updated for bf4 though
    0x5C4954A6:".itexture",
    0x2D47A5FF:".gfx",
    0x22FE8AC8:"",
    0x6BB6D7D2:".streamingstub",
    0x1CA38E06:"",
    0x15E1F32E:"",
    0x4864737B:".hkdestruction",
    0x91043F65:".hknondestruction",
    0x51A3C853:".ant",
    0xD070EED1:".animtrackdata",
    0x319D8CD0:".ragdoll",
    0x49B156D4:".mesh",
    0x30B4A553:".occludermesh",
    0x5BDFDEFE:".lightingsystem",
    0x70C5CB3E:".enlighten",
    0xE156AF73:".probeset",
    0x7AEFC446:".staticenlighten",
    0x59CEEB57:".shaderdatabase",
    0x36F3F2C0:".shaderdb",
    0x10F0E5A1:".shaderprogramdb",
    0xC6DBEE07:".mohwspecific",
    0xafecb022:".luac"
}

def readBlockHeader(f):
    #Block header is a bitfield:
    #8 bits: custom dict flag
    #24 bits: uncompressed size
    #8 bits: compression type
    #4 bits: always 7?
    #20 bits: compressed size
    num1,num2=unpack(">II",f.read(8))
    dictFlag=num1&0xFF000000
    uncompressedSize=num1&0x00FFFFFF
    comType=(num2&0xFF000000)>>24
    compressedSize=num2&0x000FFFFF
    return dictFlag, uncompressedSize, comType, compressedSize

def decompressBlock(f,f2):
    dictFlag, uncompressedSize, comType, compressedSize = readBlockHeader(f)

    if comType==0x09:
        #Block is compressed with LZ4.
        srcBuf=f.read(compressedSize)
        dstBuf=bytes(uncompressedSize)
        liblz4.LZ4_decompress_safe_partial(srcBuf,dstBuf,compressedSize,uncompressedSize,uncompressedSize)
        f2.write(dstBuf)
    elif comType==0x0f:
        #Block is compressed with Zstd.
        srcBuf=f.read(compressedSize)
        dstBuf=bytes(uncompressedSize) 
        if dictFlag:
            zstd_dctx=ctypes.c_void_p(libzstd.ZSTD_createDCtx())
            libzstd.ZSTD_decompress_usingDDict(zstd_dctx,dstBuf,uncompressedSize,srcBuf,compressedSize,zstd_dict)
            libzstd.ZSTD_freeDCtx(zstd_dctx)
        else:
            libzstd.ZSTD_decompress(dstBuf,uncompressedSize,srcBuf,compressedSize)
        f2.write(dstBuf)
    elif comType==0x15:
        #Block is compressed with Oodle. Only used in FIFA 18/19 so far.
        if not oodle: raise Exception("You need oo2core_6_win32.dll to decompress Oodle.")
        srcBuf=f.read(compressedSize)
        dstBuf=bytes(uncompressedSize)
        oodle.OodleLZ_Decompress(srcBuf,compressedSize,dstBuf,uncompressedSize,0,0,0,0,0,0,0,0,0,3)
        f2.write(dstBuf)
    elif comType==0x02:
        #Block is compressed with Zlib.
        srcBuf=f.read(compressedSize)
        dstBuf=zlib.decompress(srcBuf)
        f2.write(dstBuf)
    elif comType==0x00:
        #No compression, just write this block as it is.
        f2.write(f.read(compressedSize))
    else:
        raise Exception("Unknown compression type 0x%02x at 0x%08x in %s" % (comType,f.tell()-8,f.name))

    return uncompressedSize

def decompressPayload(srcPath,offset,size,originalSize,outPath):
    f=open(srcPath,"rb")
    f.seek(offset)
    f2=open(os.path.normpath(outPath),"wb")

    #Payloads are split into blocks and each block may or may not be compressed.
    #We need to decompress and glue the blocks together to get the real file.
    while f.tell()!=offset+size:        
        decompressBlock(f,f2)
        if originalSize and f2.tell()==originalSize:
            break

    f.close()
    f2.close()

def split1v7(num): return (num>>28,num&0x0fffffff) #0x7A945CF1 => (7, 0xA945CF1)

def decompressPatchedPayload(basePath,baseOffset,deltaPath,deltaOffset,deltaSize,originalSize,outPath,midInstructionType=-1,midInstructionSize=0):
    base=open(basePath,"rb")
    delta=open(deltaPath,"rb")
    base.seek(baseOffset)
    delta.seek(deltaOffset)
    f2=open(os.path.normpath(outPath),"wb")

    instructionType=midInstructionType
    instructionSize=midInstructionSize

    #This is where magic happens: we need to splice bits from delta bundle and base bundle.
    #See here for details: http://pastebin.com/TftZEU9q
    while delta.tell()!=deltaOffset+deltaSize:
        if instructionType==-1:
            instructionType, instructionSize = split1v7(unpack(">I",delta.read(4))[0])

        if instructionType==0: #add base blocks without modification
            for i in range(instructionSize):
                decompressBlock(base,f2)
                if f2.tell()==originalSize: break
        elif instructionType==2: #make tiny fixes in the base block
            blockSize=unpack(">H",delta.read(2))[0]+1
            deltaBlockEnd=delta.tell()+instructionSize

            baseBlock=io.BytesIO()
            baseBlockSize=decompressBlock(base,baseBlock)
            baseBlock.seek(0)

            while delta.tell()!=deltaBlockEnd:
                baseRead,baseSkip,addCount=unpack(">HBB",delta.read(4))
                f2.write(baseBlock.read(baseRead-baseBlock.tell()))
                baseBlock.seek(baseSkip,1)
                f2.write(delta.read(addCount))

            f2.write(baseBlock.read(baseBlockSize-baseBlock.tell()))
        elif instructionType==1: #make larger fixes in the base block
            baseBlock=io.BytesIO()
            baseBlockSize=decompressBlock(base,baseBlock)
            baseBlock.seek(0)

            for i in range(instructionSize):
                baseRead,baseSkip=unpack(">HH",delta.read(4))
                f2.write(baseBlock.read(baseRead-baseBlock.tell()))
                baseBlock.seek(baseSkip,1)
                decompressBlock(delta,f2)

            f2.write(baseBlock.read(baseBlockSize-baseBlock.tell()))
        elif instructionType==3: #add delta blocks directly to the payload
            for i in range(instructionSize):
                decompressBlock(delta,f2)
                if f2.tell()==originalSize: break
        elif instructionType==4: #skip entire blocks, do not increase currentSize at all
            for i in range(instructionSize):
                dictFlag, uncompressedSize, comType, compressedSize = readBlockHeader(base)
                base.seek(compressedSize,1)
        else:
            raise Exception("Unknown payload type: 0x%02x Delta offset: 0x%08x" % (instructionType,delta.tell()-0x04))

        instructionType=-1
        if f2.tell()==originalSize: break

    #May need to get the rest from the base bundle (infinite type 0 instructions).
    while f2.tell()!=originalSize:
        decompressBlock(base,f2)

    base.close()
    delta.close()
    f2.close()



def dump(tocPath,baseTocPath,outPath):
    """Take the filename of a toc and dump all files to the targetFolder."""

    #Depending on how you look at it, there can be up to 2*(3*3+1)=20 different cases:
    #    The toc has a cas flag which means all assets are stored in the cas archives. => 2 options
    #        Each bundle has either a delta or base flag, or no flag at all. => 3 options
    #            Each file in the bundle is one of three types: ebx/res/chunks => 3 options
    #        The toc itself contains chunks. => 1 option
    #
    #Simplify things by ignoring base bundles (they just state that the unpatched bundle is used),
    #which is alright, as the user needs to dump the unpatched files anyway.
    #
    #Additionally, add some common fields to the ebx/res/chunks entries so they can be treated the same.
    #=> 6 cases.

    toc=dbo.readToc(tocPath)
    if not (toc.get("bundles") or toc.get("chunks")): return #there's nothing to extract (the sb might not even exist)

    sbPath=tocPath[:-3]+"sb"
    sb=open(sbPath,"rb")

    chunkPathToc=os.path.join(outPath,"chunks")
    bundlePath=os.path.join(outPath,"bundles")
    ebxPath=os.path.join(bundlePath,"ebx")
    resPath=os.path.join(bundlePath,"res")
    chunkPath=os.path.join(bundlePath,"chunks")

    ###read the bundle depending on the four types (+cas+delta, +cas-delta, -cas+delta, -cas-delta) and choose the right function to write the payload
    if toc.get("cas"):
        for tocEntry in toc.get("bundles"): #id offset size, size is redundant
            if tocEntry.get("base"): continue #Patched bundle. However, use the unpatched bundle because no file was patched at all.

            sb.seek(tocEntry.get("offset"))
            bundle=dbo.DbObject(sb)

            #make empty lists for every type to get rid of key errors(=> less indendation)
            for listType in ("ebx","res","chunks"):
                if bundle.get(listType)==None:
                    bundle.set(listType,list())
                    
            #The noncas chunks already have originalSize calculated in Bundle.py (it was necessary to seek through the entries).
            #Calculate it for the cas chunks too. From here on, both cas and noncas ebx/res/chunks (within bundles) have size and originalSize.
            for chunk in bundle.get("chunks"):
                chunk.set("originalSize",chunk.get("logicalOffset")+chunk.get("logicalSize"))
                    
            #pick the right function
            if tocEntry.get("delta"):
                writePayload=casPatchedPayload
            else:
                writePayload=casPayload

            for entry in bundle.get("ebx"): #name sha1 size originalSize
                path=os.path.join(ebxPath,entry.get("name")+".ebx")
                writePayload(entry,path)

            for entry in bundle.get("res"): #name sha1 size originalSize resRid resType resMeta
                path=os.path.join(resPath,entry.get("name")+".res")
                writePayload(entry,path)

            for entry in bundle.get("chunks"): #id sha1 size logicalOffset logicalSize chunkMeta::meta
                path=os.path.join(chunkPath,formatGuid(entry.get("id"),False)+".chunk")
                writePayload(entry,path)

        #Deal with the chunks which are defined directly in the toc.
        #These chunks do NOT know their originalSize.
        for entry in toc.get("chunks"): # id sha1
            targetPath=os.path.join(chunkPathToc,formatGuid(entry.get("id"),False)+".chunk")
            casChunkPayload(entry,targetPath)
    else:
        for tocEntry in toc.get("bundles"): #id offset size, size is redundant
            if tocEntry.get("base"): continue #Patched bundle. However, use the unpatched bundle because no file was patched at all.

            sb.seek(tocEntry.get("offset"))

            if tocEntry.get("delta"):
                #The sb currently points at the delta file.
                #Read the unpatched toc of the same name to get the base bundle.
                baseToc=dbo.readToc(baseTocPath)
                for baseTocEntry in baseToc.get("bundles"):
                    if baseTocEntry.get("id").lower() == tocEntry.get("id").lower():
                        break
                else: #if no base bundle has with this name has been found:
                    pass #use the last base bundle. This is okay because it is actually not used at all (the delta has uses instructionType 3 only).
                    
                basePath=baseTocPath[:-3]+"sb"
                base=open(basePath,"rb")
                base.seek(baseTocEntry.get("offset"))
                bundle=noncas.patchedBundle(base, sb) #create a patched bundle using base and delta
                base.close()
                writePayload=noncasPatchedPayload
                sourcePath=[basePath,sbPath] #base, delta
            else:
                bundle=noncas.unpatchedBundle(sb)
                writePayload=noncasPayload
                sourcePath=sbPath

            for entry in bundle.ebx:
                path=os.path.join(ebxPath,entry.name+".ebx")
                writePayload(entry,path,sourcePath)

            for entry in bundle.res:
                path=os.path.join(resPath,entry.name+".res")
                writePayload(entry,path,sourcePath)

            for entry in bundle.chunks:
                path=os.path.join(chunkPath,formatGuid(entry.id,True)+".chunk")
                writePayload(entry,path,sourcePath)

        #Deal with the chunks which are defined directly in the toc.
        #These chunks do NOT know their originalSize.
        for entry in toc.get("chunks"): # id offset size
            targetPath=os.path.join(chunkPathToc,formatGuid(entry.get("id"),False)+".chunk")
            noncasChunkPayload(entry,targetPath,sbPath)

    sb.close()



def prepareDir(targetPath):
    if os.path.exists(targetPath): return True
    dirName=os.path.dirname(targetPath)
    if not os.path.exists(dirName): os.makedirs(dirName) #make the directory for the dll
    #print(targetPath)

def formatGuid(data,bigEndian):
    guid=ebx.Guid(data,bigEndian)
    return guid.format()

#for each bundle, the dump script selects one of these six functions
def casPayload(bundleEntry, targetPath):
    #Some files may be from localizations user doesn't have installed.
    try:
        if prepareDir(targetPath): return
        catEntry=cat[bundleEntry.get("sha1")]
        decompressPayload(catEntry.path,catEntry.offset,catEntry.size,bundleEntry.get("originalSize"),targetPath)
    except:
        return

def casPatchedPayload(bundleEntry, targetPath):
    if prepareDir(targetPath): return

    if bundleEntry.get("casPatchType")==2:
        catDelta=cat[bundleEntry.get("deltaSha1")]
        catBase=cat[bundleEntry.get("baseSha1")]
        decompressPatchedPayload(catBase.path,catBase.offset,
                                 catDelta.path,catDelta.offset,catDelta.size,
                                 bundleEntry.get("originalSize"),targetPath)
    else:
        casPayload(bundleEntry, targetPath) #if casPatchType is not 2, use the unpatched function.

def casChunkPayload(entry,targetPath):
    #Some files may be from localizations user doesn't have installed.
    try:
        if prepareDir(targetPath): return
        catEntry=cat[entry.get("sha1")]
        decompressPayload(catEntry.path,catEntry.offset,catEntry.size,None,targetPath)
    except:
        return

def noncasPayload(entry, targetPath, sourcePath):
    if prepareDir(targetPath): return
    decompressPayload(sourcePath,entry.offset,entry.size,entry.originalSize,targetPath)

def noncasPatchedPayload(entry, targetPath, sourcePath):
    if prepareDir(targetPath): return
    decompressPatchedPayload(sourcePath[0], entry.baseOffset,#entry.baseSize,
                            sourcePath[1], entry.deltaOffset, entry.deltaSize,
                            entry.originalSize, targetPath,
                            entry.midInstructionType, entry.midInstructionSize)

def noncasChunkPayload(entry, targetPath, sourcePath):
    if prepareDir(targetPath): return
    decompressPayload(sourcePath,entry.get("offset"),entry.get("size"),None,targetPath)



#Take a dict and fill it using a cat file: sha1 vs (offset, size, cas path)
#Cat files are always little endian.
class CatEntry:
    def __init__(self,f,casDirectory,version):
        self.sha1=f.read(20)
        self.offset,self.size=unpack("<II",f.read(8))
        if version!=1: self.unk=unpack("<I",f.read(4))
        casNum=unpack("<I",f.read(4))
        self.path=os.path.join(casDirectory,"cas_%02d.cas" % casNum)

def readCat1(catDict,catPath):
    #2013, original version.
    cat=dbo.unXor(catPath)
    cat.seek(0,2) #get eof
    catSize=cat.tell()
    cat.seek(16) #skip nyan
    casDirectory=os.path.dirname(catPath)

    while cat.tell()<catSize:
        catEntry=CatEntry(cat,casDirectory,1)
        catDict[catEntry.sha1]=catEntry

def readCat2(catDict,catPath):
    #2015, added the number of entries in the header, a new var (always 0?) to cat entry and a new section with unknown data (usually empty).
    cat=dbo.unXor(catPath)
    cat.seek(0,2) #get eof
    cat.seek(16) #skip nyan
    numEntries,numEntries2=unpack("<II",cat.read(8))
    casDirectory=os.path.dirname(catPath)

    for i in range(numEntries):
        catEntry=CatEntry(cat,casDirectory,2)
        catDict[catEntry.sha1]=catEntry

def readCat3(catDict,catPath):
    #2017, added another unknown section, increased change entry counts to 64-bit(?).
    cat=dbo.unXor(catPath)
    cat.seek(0,2) #get eof
    cat.seek(16) #skip nyan
    numEntries, numEntries2, numEntries3 = unpack("<QQQ",cat.read(24))
    casDirectory=os.path.dirname(catPath)

    for i in range(numEntries):
        catEntry=CatEntry(cat,casDirectory,3)
        catDict[catEntry.sha1]=catEntry

def dumpRoot(dataDir,patchDir,outPath):
    for dir0, dirs, ff in os.walk(dataDir):
        for fname in ff:
            if fname[-4:]==".toc":
                fname=os.path.join(dir0,fname)
                localPath=os.path.relpath(fname,dataDir)
                print(localPath)

                #Check if there's a patched version and extract it first.
                patchedName=os.path.join(patchDir,localPath)
                if os.path.isfile(patchedName):
                    dump(patchedName,fname,outPath)

                dump(fname,None,outPath)


#make the paths absolute and normalize the slashes
gameDirectory=os.path.normpath(gameDirectory)
targetDirectory=os.path.normpath(targetDirectory) #it's an absolute path already

#Load compression dictionary.
f=open("comp_dict.bin","rb")
compDictBuf=f.read()
f.close()
zstd_dict=ctypes.c_void_p(libzstd.ZSTD_createDDict(compDictBuf,len(compDictBuf)))

cat=dict()

#Load layout.toc
tocLayout=dbo.readToc(os.path.join(gameDirectory,"Data","layout.toc"))
if not tocLayout.getSubEntry("installManifest"):
    #Old layout similar to Frostbite 2 with a single cas.cat.
    #Can also be non-cas.
    dataDir=os.path.join(gameDirectory,"Data")
    updateDir=os.path.join(gameDirectory,"Update")
    patchDir=os.path.join(updateDir,"Patch","Data")

    readCat=readCat1

    catPath=os.path.join(dataDir,"cas.cat") #Seems to always be in the same place
    if os.path.isfile(catPath):
        print("Reading cat entries...")
        readCat(cat,catPath)

        #Check if there's a patched version.
        patchedCat=os.path.join(patchDir,os.path.relpath(catPath,dataDir))
        if os.path.isfile(patchedCat):
            print("Reading patched cat entries...")
            readCat(cat,patchedCat)

    if os.path.isdir(updateDir):
        #First, extract all DLC.
        for dir in os.listdir(updateDir):
            if dir=="Patch":
                continue

            print("Extracting DLC %s..." % dir)
            dumpRoot(os.path.join(updateDir,dir,"Data"),patchDir,targetDirectory)

    #Now extract the base game.
    print("Extracting main game...")
    dumpRoot(dataDir,patchDir,targetDirectory)
else:
    #New version with multiple cats split into install groups, seen in 2015 and later games.
    #Appears to always use cas.cat and never use delta bundles, patch just replaces bundles fully.
    dataDir=os.path.join(gameDirectory,"Data")
    patchDir=os.path.join(gameDirectory,"Patch")

    #Load patched layout.toc so we know about DLCs.
    patchedLayout=os.path.join(patchDir,os.path.join(patchDir,"layout.toc"))
    if os.path.isfile(patchedLayout):
        tocLayout=dbo.readToc(patchedLayout)

    #Detect cat version.
    if tocLayout.getSubEntry("installManifest").get("maxTotalSize"):
        readCat=readCat2
    else:
        readCat=readCat3

    #Read all cat files.
    for entry in tocLayout.getSubEntry("installManifest").get("installChunks"):
        catName=entry.get("installBundle")      
        if not catName:
            continue

        #Allow skipping optional install chunks (localizations and optional DLCs).
        catPath=os.path.join(dataDir,os.path.normpath(catName),"cas.cat")
        if not entry.get("Language") and not entry.get("optionalDLC"):
            if not os.path.isfile(catPath):
                raise Exception("Cat does not exist: %s" % catPath)

        print("Reading %s/cas.cat..." % catName)        
        readCat(cat,catPath)

        #Check if there's a patched version.
        patchedCat=os.path.join(patchDir,os.path.relpath(catPath,dataDir))
        if os.path.isfile(patchedCat):
            print("Reading patched %s/cas.cat..." % catName)
            readCat(cat,patchedCat)

    print("Extracting game...")
    dumpRoot(dataDir,patchDir,targetDirectory)

libzstd.ZSTD_freeDDict(zstd_dict)
