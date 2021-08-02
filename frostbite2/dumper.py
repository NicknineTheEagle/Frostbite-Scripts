#This script runs through all toc files it can find and uses that information to extract the files to a target directory.
#Often the assets are actually stored in cascat archives (the sbtoc knows where to search in the cascat), which is taken care of too.
#The script does not overwrite existing files (mainly because 10 sbtocs pointing at the same asset in the cascat would make the extraction time unbearable).
import dbo
import noncas
import ebx
import os
from struct import pack,unpack
import io
import sys
import zlib
import subprocess
import shutil
import res

#Adjust paths here.
#do yourself a favor and don't dump into the Users folder (or it might complain about permission)

gameDirectory   = r"D:\Games\OriginGames\Need for Speed The Run"
targetDirectory = r"E:\GameRips\NFS\NFSTR\pc\dump"

#####################################
#####################################

def makeLongDirs(path):
    folderPath=lp(os.path.dirname(path))
    os.makedirs(folderPath,exist_ok=True)

def open2(path,mode):
    #create folders if necessary and return the file handle
    if "w" in mode: makeLongDirs(path)
    return open(lp(path),mode)

def lp(path): #long pathnames
    if path[:4]=='\\\\?\\' or path=="" or len(path)<=247: return path
    return '\\\\?\\' + os.path.normpath(path)



def dump(tocPath,outPath,baseTocPath=None,commonDatPath=None):
    toc=dbo.readToc(tocPath)
    if not (toc.get("bundles") or toc.get("chunks")): return #there's nothing to extract (the sb might not even exist)

    sbPath=tocPath[:-3]+"sb"
    sb=openSbFile(sbPath)

    chunkPathToc=os.path.join(outPath,"chunks")
    bundlePath=os.path.join(outPath,"bundles")
    ebxPath=os.path.join(bundlePath,"ebx")
    dbxPath=os.path.join(bundlePath,"dbx")
    resPath=os.path.join(bundlePath,"res")
    chunkPath=os.path.join(bundlePath,"chunks")

    if toc.get("cas"):
        #deal with cas bundles => ebx, dbx, res, chunks.
        for tocEntry in toc.get("bundles"): #id offset size, size is redundant
            sb.seek(tocEntry.get("offset"))
            bundle=dbo.DbObject(sb)

            for entry in bundle.get("ebx",list()): #name sha1 size originalSize
                compressed=(entry.get("size")!=entry.get("originalSize"))
                path=os.path.join(ebxPath,entry.get("name")+".ebx")
                casBundlePayload(entry,path,compressed)
                ebx.addEbxGuid(path,ebxPath)

            for entry in bundle.get("dbx",list()): #name sha1 size originalSize
                if entry.get("idata"): #dbx appear only idata if at all, they are probably deprecated and were not meant to be shipped at all.
                    path=os.path.join(dbxPath,entry.get("name")+".dbx")
                    out=open2(path,"wb")
                    out.write(zlibIdata(entry.get("idata")))
                    out.close()

            for entry in bundle.get("res",list()): #name sha1 size originalSize resType resMeta
                res.addToResTable(entry.get("name"),entry.get("resType"),entry.get("resMeta"))
                path=os.path.join(resPath,entry.get("name")+res.getResExt(entry.get("resType")))
                casBundlePayload(entry,path,True)

            for entry in bundle.get("chunks",list()): #id sha1 size chunkMeta::h32 chunkMeta::meta
                path=os.path.join(chunkPath,entry.get("id").format()+".chunk")
                casBundlePayload(entry,path,entry.get("id").isChunkCompressed())

        #deal with cas chunks defined in the toc.
        for entry in toc.get("chunks"): #id sha1
            path=os.path.join(chunkPathToc,entry.get("id").format()+".chunk")
            casChunkPayload(entry,path)

    else:
        #deal with noncas bundles
        for tocEntry in toc.get("bundles"): #id offset size, size is redundant
            if tocEntry.get("base"): continue #Patched noncas bundle. However, use the unpatched bundle because no file was patched at all.

            sb.seek(tocEntry.get("offset"))

            if tocEntry.get("delta"):
                #Patched noncas bundle. Here goes the hilarious part. Take the patched data and glue parts from the unpatched data in between.
                #When that is done (in memory of course) the result is a new valid bundle file that can be read like an unpatched one.

                deltaSize,deltaMagic,padding=unpack(">IIQ",sb.read(16))

                class Delta:
                    def __init__(self,sb):
                        self.size,self.typ,self.offset=unpack(">IiQ",sb.read(16))

                deltas=list()
                for deltaEntry in range(deltaSize//16):
                    deltas.append(Delta(sb))

                bundleStream=io.BytesIO() #here be the new bundle data
                unpatchedSb=openSbFile(baseTocPath[:-3]+"sb")
                commonDat=open(commonDatPath,"rb") if os.path.isfile(commonDatPath) else None

                for delta in deltas:
                    if delta.typ==1:
                        unpatchedSb.seek(delta.offset)
                        bundleStream.write(unpatchedSb.read(delta.size))
                    elif delta.typ==0:
                        bundleStream.write(sb.read(delta.size))
                    elif delta.typ==-1:
                        if not commonDat: raise Exception("Found delta type -1 without common.dat present.")
                        commonDat.seek(delta.offset)
                        bundleStream.write(commonDat.read(delta.size))
                    else:
                        raise Exception("Unknown delta type %d in patched bundle at 0x%08x" % (delta.typ,tocEntry.get("offset")))

                unpatchedSb.close()
                if commonDat: commonDat.close()
                bundleStream.seek(0)

                bundle=noncas.Bundle(bundleStream)
                sb2=bundleStream
            else:
                bundle=noncas.Bundle(sb)
                sb2=sb

            for entry in bundle.ebxEntries:
                compressed=(entry.size!=entry.originalSize)
                path=os.path.join(ebxPath,entry.name+".ebx")
                noncasBundlePayload(sb2,entry,path,compressed)
                ebx.addEbxGuid(path,ebxPath)

            for entry in bundle.resEntries:
                res.addToResTable(entry.name,entry.resType,entry.resMeta)
                path=os.path.join(resPath,entry.name+res.getResExt(entry.resType))
                noncasBundlePayload(sb2,entry,path,True)

            for entry in bundle.chunkEntries:
                path=os.path.join(chunkPath,entry.id.format()+".chunk")
                noncasBundlePayload(sb2,entry,path,entry.id.isChunkCompressed())

        #deal with noncas chunks defined in the toc
        for entry in toc.get("chunks"): #id offset size
            path=os.path.join(chunkPathToc,entry.get("id").format()+".chunk")
            noncasChunkPayload(sb,entry,path)

    #Clean up.
    sb.close()
    if os.path.isdir(tempDirectory):
        shutil.rmtree(tempDirectory)



def casBundlePayload(entry,outPath,compressed):
    if os.path.isfile(lp(outPath)): return

    out=open2(outPath,"wb")
    catEntry=cat[entry.get("sha1")]
    cas=open(catEntry.path,"rb")
    cas.seek(catEntry.offset)
    if compressed: out.write(zlibb(cas,catEntry.size))
    else:          out.write(cas.read(catEntry.size))
    cas.close()
    out.close()

def casChunkPayload(entry,outPath):
    if os.path.isfile(lp(outPath)): return

    catEntry=cat[entry.get("sha1")]
    out=open2(outPath,"wb")
    cas=open(catEntry.path,"rb")
    cas.seek(catEntry.offset)
    if entry.get("id").isChunkCompressed():
        out.write(zlibb(cas,catEntry.size))
    else:
        out.write(cas.read(catEntry.size))
    cas.close()
    out.close()

def noncasBundlePayload(sb,entry,outPath,compressed):
    if os.path.isfile(lp(outPath)): return

    sb.seek(entry.offset)
    out=open2(outPath,"wb")
    if compressed:
        out.write(zlibb(sb,entry.size))
    else:
        out.write(sb.read(entry.size))
    out.close()

def noncasChunkPayload(sb,entry,outPath):
    if os.path.isfile(lp(outPath)): return

    sb.seek(entry.get("offset"))
    out=open2(outPath,"wb")
    if entry.get("id").isChunkCompressed():
        out.write(zlibb(sb,entry.get("size")))
    else:
        out.write(sb.read(entry.get("size")))
    out.close()

#zlib:
#Compressed files are split into blocks which are then zlibbed individually (prefixed with compressed and uncompressed size)
#and finally glued together again. Uncompressed files, on the other hand, are not blocked, they are just the payload.
#EBX are uncompressed in BF3 and NFS:TR and compressed in MOH:WF and AOT:DC. Since EBX have a lot of text and a lot of zeroes
#they are guaranteed to be smaller when compressed so we can safely check if size!=originalSize.
#RES are always compressed.
#For chunks, the last bit in GUID is set for compressed payload.

def zlibb(f,size):
    outStream=io.BytesIO()
    startOffset=f.tell()
    while f.tell()<startOffset+size-8:
        uncompressedSize,compressedSize=unpack(">II",f.read(8)) #big endian
        data=f.read(compressedSize)

        #TODO: Some blocks in BF3 are apparently uncompressed? Not sure what's going on here.
        try:
            outStream.write(zlib.decompress(data))
        except:
            outStream.write(data)

    data=outStream.getvalue()
    outStream.close()
    return data

def zlibIdata(bytestring):
    return zlibb(io.BytesIO(bytestring),len(bytestring))



def openSbFile(sbPath):
    sb=open(sbPath,"rb")
    magic=sb.read(4)
    if magic==b"\x0F\xF5\x12\xED":
        #X360 compressed file.
        #Decompress it into a temporary file with the tool, we'll clean it up once we're done.
        sb.close()
        decSbPath=os.path.join(tempDirectory,os.path.relpath(sbPath,gameDirectory))
        subprocess.run([r"..\thirdparty\xbdecompress.exe","/T","/Y",sbPath,decSbPath])
        return open(decSbPath,"rb")

    #Normal SB file.
    sb.seek(0)
    return sb



#Take a dict and fill it using a cat file: sha1 vs (offset, size, cas path)
#Cat files are always little endian.
class CatEntry:
    def __init__(self,f,casDirectory):
        self.sha1=f.read(20)
        self.offset, self.size, casNum = unpack("<III",f.read(12))
        self.path=os.path.join(casDirectory,"cas_%02d.cas" % casNum)

def readCat(catDict, catPath):
    cat=dbo.unXor(catPath)
    cat.seek(0,2) #get eof
    catSize=cat.tell()
    cat.seek(16) #skip nyan
    casDirectory=os.path.dirname(catPath)
    while cat.tell()!=catSize:
        catEntry=CatEntry(cat,casDirectory)
        catDict[catEntry.sha1]=catEntry

def dumpRoot(dataDir,patchDir,outPath):
    os.makedirs(outPath,exist_ok=True)
    commonDatPath=os.path.join(patchDir,"common.dat")

    for dir0, dirs, ff in os.walk(dataDir):
        for fname in ff:
            if fname[-4:]==".toc":
                fname=os.path.join(dir0,fname)
                localPath=os.path.relpath(fname,dataDir)
                print(localPath)

                #Check if there's a patched version and extract it first.
                patchedName=os.path.join(patchDir,localPath)
                if os.path.isfile(patchedName):
                    dump(patchedName,outPath,fname,commonDatPath)

                dump(fname,outPath)


#make the paths absolute and normalize the slashes
gameDirectory=os.path.normpath(gameDirectory)
targetDirectory=os.path.normpath(targetDirectory) #it's an absolute path already

tempDirectory=os.path.join(targetDirectory,"temp")

dataDir=os.path.join(gameDirectory,"Data")
updateDir=os.path.join(gameDirectory,"Update")
patchDir=os.path.join(updateDir,"Patch","Data")

print("Loading RES names...")
res.loadResNames()

#read cat file
cat=dict()
catPath=os.path.join(dataDir,"cas.cat") #Seems to always be in the same place.
if os.path.isfile(catPath):
    print("Reading cat entries...")
    readCat(cat,catPath)

    #Check if there's a patched version.
    patchedCat=os.path.join(patchDir,os.path.relpath(catPath,dataDir))
    if os.path.isfile(patchedCat):
        print("Reading patched cat entries...")
        readCat(cat,patchedCat)

if os.path.isdir(updateDir):
    #First, extract all DLCs.
    for dir in os.listdir(updateDir):
        if dir=="Patch":
            continue

        print("Extracting DLC %s..." % dir)
        dumpRoot(os.path.join(updateDir,dir,"Data"),patchDir,targetDirectory)

#Now extract the base game.
print("Extracting main game...")
dumpRoot(dataDir,patchDir,targetDirectory)

if not os.path.isdir(targetDirectory):
    print("Nothing was extracted, did you set input path correctly?")
    sys.exit(1)

print("Writing EBX GUID table...")
ebx.writeGuidTable(targetDirectory)

print ("Writing RES table...")
res.writeResTable(targetDirectory)

#MOH:WF hack: extract driving levels assets.
if os.path.isdir(os.path.join(gameDirectory,"game","Speed")):
    print("Extracting MOH:WF driving assets...")
    gameDirectory=os.path.join(gameDirectory,"game")
    targetDirectory=os.path.join(targetDirectory,"speed")
    dataDir=os.path.join(gameDirectory,"Speed")
    updateDir=os.path.join(gameDirectory,"Update")
    patchDir=os.path.join(updateDir,"Patch","Speed")
    ebx.guidTable.clear()
    res.resTable.clear()
    res.unkResTypes.clear()
    dumpRoot(dataDir,patchDir,targetDirectory)

    print("Writing EBX GUID table...")
    ebx.writeGuidTable(targetDirectory)

    print ("Writing RES table...")
    res.writeResTable(targetDirectory)
