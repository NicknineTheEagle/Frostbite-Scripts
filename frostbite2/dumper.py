#This script runs through all toc files it can find and uses that information to extract the files to a target directory.
#Often the assets are actually stored in cascat archives (the sbtoc knows where to search in the cascat), which is taken care of too.
#The script does not overwrite existing files (mainly because 10 sbtocs pointing at the same asset in the cascat would make the extraction time unbearable).
import dbo
import noncas
import os
from struct import pack,unpack
import io
import sys
import zlib
import subprocess
import ebx

#Adjust paths here.
#do yourself a favor and don't dump into the Users folder (or it might complain about permission)

# Some X360 games have some SB files compressed with X360 compression. Point this at your xbdecompress.exe so that they can be decompressed.
xbdecompressPath=r"E:\Utilities\xbcompress\xbdecompress.exe"

gameDirectory=r"E:\Games\EA\NFSTheRun"
targetDirectory=r"E:\GameRips\NFS\NFSTR\pc\dump"

#####################################
#####################################

resTypes={
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
    0xC6DBEE07:".mohwspecific"
}

#zlib (one more try):
#Files are split into pieces which are then zlibbed individually (prefixed with compressed and uncompressed size)
#and finally glued together again. Non-zlib files on the other hand have no prefix about size, they are just the payload.
#The archive or file does not declare zlib/nonzlib, making things really complicated. I think the engine actually uses
#ebx and res to figure out if a chunk is zlib or not. However, res itself is zlibbed already; in mohw ebx is zlibbed too.
#In particular mohw crashes when delivering a non-zlibbed ebx file.
#Prefixing the payload with two identical ints containing the payload size makes mohw work again so the game really deduces
#compressedSize==uncompressedSize => uncompressed payload.

#some thoughts without evidence:
#It's possible that ebx/res zlib is slightly different from chunk zlib.
#Maybe for ebx/res, compressedSize==uncompressedSize always means an uncompressed piece.
#Whereas for chunks (textures in particular), there are mip sizes to consider
#e.g. first piece of a mip is always compressed (even with compressedSize==uncompressedSize) but subsequent pieces of a mip may be uncompressed.

def zlibb(f, size):
    #if the entire file is < 10 bytes, it must be non zlib
    if size<10: return f.read(size)

    #interpret the first 10 bytes as fb2 zlib stuff
    uncompressedSize,compressedSize=unpack(">ii",f.read(8))
    magic=f.read(2)
    f.seek(-10,1)

    #sanity check: compressedSize may be just random non-zlib payload.
    if compressedSize>size-8: return f.read(size)
    if compressedSize<=0 or uncompressedSize<=0: return f.read(size)

    #another sanity check with a very specific condition:
    #when uncompressedSize is different from compressedSize, then having a non-zlib piece makes no sense.
    #alternatively one could just let the zlib module try to handle this.
    #It's tempting to compare uncompressedSize<compressedSize, but there are indeed cases when
    #the uncompressed payload is smaller than the compressed one.
    if uncompressedSize!=compressedSize and magic!=b"\x78\xda":
        return f.read(size)
    
    outStream=io.BytesIO()
    pos0=f.tell()
    while f.tell()<pos0+size-8:
        uncompressedSize,compressedSize=unpack(">ii",f.read(8)) #big endian
        
        #sanity checks:
        #The sizes may be just random non-zlib payload; as soon as that happens,
        #abandon the whole loop and just give back the full payload without decompression
        if compressedSize<=0 or uncompressedSize<=0:
            f.seek(pos0)
            return f.read(size)
        #likewise, make sure that compressed size does not exceed the size of the file
        if f.tell()+compressedSize>pos0+size:
            f.seek(pos0)
            return f.read(size)

        #try to decompress
        if compressedSize!=uncompressedSize:
            try:    outStream.write(zlib.decompress(f.read(compressedSize)))
            except: outStream.write(f.read(compressedSize))
        else:
            #if compressed==uncompressed, one might be tempted to think that it is always non-zlib. It's not.
            magic=f.read(2)
            f.seek(-2,1)
            if magic==b"\x78\xda":
                try:    outStream.write(zlib.decompress(f.read(compressedSize)))
                except: outStream.write(f.read(compressedSize))
            else:
                outStream.write(f.read(compressedSize))
 
    data=outStream.getvalue()
    outStream.close()
    return data


def zlibIdata(bytestring):
    return zlibb(io.BytesIO(bytestring),len(bytestring))

def open2(path,mode):
    #create folders if necessary and return the file handle

    #first of all, create one folder level manully because makedirs might fail
    pathParts=path.split("\\")
    manualPart="\\".join(pathParts[:2])
    if not os.path.isdir(manualPart): os.makedirs(manualPart)

    #now handle the rest, including extra long path names
    folderPath=lp(os.path.dirname(path))
    if not os.path.isdir(folderPath): os.makedirs(folderPath)
    return open(lp(path),mode)

def lp(path): #long pathnames
    if path[:4]=='\\\\?\\' or path=="" or len(path)<=247: return os.path.normpath(path)
    return unicode('\\\\?\\' + os.path.normpath(path))

class Delta:
    def __init__(self,sb):
        self.size,self.fromUnpatched,self.offset=unpack(">IIQ",sb.read(16))

def dump(tocPath,baseTocPath,outPath):
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
            bundle=dbo.Entry(sb)

            #make empty lists for every type to get rid of key errors(=> less indendation)
            for listType in ("ebx","dbx","res","chunks"):
                if bundle.get(listType) == None:
                    bundle.set(listType,list())

            for entry in bundle.get("ebx"): #name sha1 size originalSize
                path=os.path.join(ebxPath,entry.get("name")+".ebx")
                casHandlePayload(entry,path)

            for entry in bundle.get("dbx"): #name sha1 size originalSize
                if entry.get("idata"): #dbx appear only idata if at all, they are probably deprecated and were not meant to be shipped at all.
                    out=open2(os.path.join(dbxPath,entry.get("name")+".dbx"),"wb")
                    if entry.get("size")==entry.get("originalSize"):
                        out.write(entry.get("idata"))
                    else:          
                        out.write(zlibIdata(entry.get("idata")))
                    out.close()

            for entry in bundle.get("res"): #name sha1 size originalSize resType resMeta
                path=os.path.join(resPath,entry.get("name")+".res")
                casHandlePayload(entry,path)

            for entry in bundle.get("chunks"): #id sha1 size, chunkMeta::meta
                path=os.path.join(chunkPath,formatGuid(entry.get("id"),False)+".chunk")
                casHandlePayload(entry,path)

        #deal with cas chunks defined in the toc.
        for entry in toc.get("chunks"): # id sha1
            path=os.path.join(chunkPathToc,formatGuid(entry.get("id"),False)+".chunk")
            casHandlePayload(entry,path)

    else:
        #deal with noncas bundles
        for tocEntry in toc.get("bundles"): #id offset size, size is redundant         
            if tocEntry.get("base"): continue #Patched noncas bundle. However, use the unpatched bundle because no file was patched at all.
            ## So I just skip the entire process and expect the user to extract all unpatched files on his own.

            sb.seek(tocEntry.get("offset"))
            
            if tocEntry.get("delta"):
                #Patched noncas bundle. Here goes the hilarious part. Take the patched data and glue parts from the unpatched data in between.
                #When that is done (in memory of course) the result is a new valid bundle file that can be read like an unpatched one.

                deltaSize,DELTAAAA,nulls=unpack(">IIQ",sb.read(16))
                deltas=[]
                for deltaEntry in range(deltaSize//16):
                    deltas.append(Delta(sb))

                bundleStream=io.BytesIO() #here be the new bundle data
                patchedOffset=sb.tell()

                unpatchedPath=baseTocPath[:-3]+"sb"
                unpatchedSb=openSbFile(unpatchedPath)

                for delta in deltas:
                    if not delta.fromUnpatched:
                        bundleStream.write(sb.read(delta.size))
                    else:
                        unpatchedSb.seek(delta.offset)
                        bundleStream.write(unpatchedSb.read(delta.size))
                unpatchedSb.close()
                bundleStream.seek(0)    

                bundle=noncas.Bundle(bundleStream)
                sb2=bundleStream           
            else:
                bundle=noncas.Bundle(sb)
                sb2=sb

            for entry in bundle.ebxEntries:
                path=os.path.join(ebxPath,entry.name+".ebx")
                noncasHandlePayload(sb2,entry.offset,entry.size,entry.originalSize,path)

            for entry in bundle.resEntries:
                originalSize=entry.originalSize
                path=os.path.join(resPath,entry.name+".res")
                noncasHandlePayload(sb2,entry.offset,entry.size,entry.originalSize,path)

            for entry in bundle.chunkEntries:
                path=os.path.join(chunkPath,formatGuid(entry.id,True)+".chunk")
                noncasHandlePayload(sb2,entry.offset,entry.size,None,path)

        #deal with noncas chunks defined in the toc
        for entry in toc.get("chunks"): #id offset size
            path=os.path.join(chunkPathToc,formatGuid(entry.get("id"),False)+".chunk")
            noncasHandlePayload(sb,entry.get("offset"),entry.get("size"),None,path)

    # Clean up.
    sb.close()
    for tempSb in tempSbFiles:
        os.remove(tempSb)
    tempSbFiles.clear()



def formatGuid(data,bigEndian):
    guid=ebx.Guid(data,bigEndian)
    return guid.format()

def casHandlePayload(entry,outPath):
    if os.path.exists(lp(outPath)): return #don't overwrite existing files to speed up things
    #print(lp(outPath))

    if entry.get("originalSize"):
        compressed=False if entry.get("size")==entry.get("originalSize") else True #I cannot tell for certain if this is correct. I do not have any negative results though.
    else:
        compressed=True

    if entry.get("idata"):
        out=open2(outPath,"wb")
        if compressed: out.write(zlibIdata(entry.get("idata")))
        else:          out.write(entry.get("idata"))
    else:        
        catEntry=cat[entry.get("sha1")]
        out=open2(outPath,"wb")
        cas=open(catEntry.path,"rb")
        cas.seek(catEntry.offset)
        if compressed: out.write(zlibb(cas,catEntry.size))
        else:          out.write(cas.read(catEntry.size))
        cas.close()
    out.close()

def noncasHandlePayload(sb,offset,size,originalSize,outPath):
    if os.path.exists(lp(outPath)): return
    #print(lp(outPath))

    sb.seek(offset)
    out=open2(outPath,"wb")
    if originalSize:
        if size==originalSize:
            out.write(sb.read(size))
        else:
            out.write(zlibb(sb,size))
    else:
        out.write(zlibb(sb,size))
    out.close()

tempSbFiles=list()

def openSbFile(sbPath):
    sb=open(sbPath,"rb")
    magic=sb.read(4)
    if magic==b"\x0F\xF5\x12\xED":
        #X360 compressed file.
        #Decompress it into a temporary file with the tool, we'll clean it up once we're done.
        sb.close()
        decSbPath=os.path.join(targetDirectory,os.path.basename(sbPath))
        subprocess.call([xbdecompressPath,"/T","/Y",sbPath,decSbPath])
        tempSbFiles.append(decSbPath)
        return open(decSbPath,"rb")

    #Normal SB file.
    sb.seek(0)
    return sb



#Take a dict and fill it using a cat file: sha1 vs (offset, size, cas path)
#Cat files are always little endian.
class CatEntry:
    def __init__(self,f,casDirectory):
        self.offset, self.size, casNum = unpack("<III",f.read(12))
        self.path=os.path.join(casDirectory,"cas_%02d.cas" % casNum)

def readCat(catDict, catPath):
    cat=dbo.unXor(catPath)
    cat.seek(0,2) #get eof
    catSize=cat.tell()
    cat.seek(16) #skip nyan
    casDirectory=os.path.dirname(catPath)
    while cat.tell()<catSize:
        sha1=cat.read(20)
        catDict[sha1]=CatEntry(cat,casDirectory)



#make the paths absolute and normalize the slashes
gameDirectory=os.path.normpath(gameDirectory)
targetDirectory=os.path.normpath(targetDirectory) #it's an absolute path already

updateDirectory=os.path.join(gameDirectory,"Update")
patchDirectory=os.path.join(updateDirectory,"Patch")

def dumpRoot(root):
    dataPath=os.path.join(root,"Data")
    for dir0, dirs, ff in os.walk(dataPath):
        for fname in ff:
            if fname[-4:]==".toc":
                fname=os.path.join(dir0,fname)
                localPath=os.path.relpath(fname,dataPath)
                print(localPath)

                #Check if there's a patched version and extract it first.
                patchedName=os.path.join(patchDirectory,"Data",localPath)
                if os.path.isfile(patchedName):
                    dump(patchedName,fname,targetDirectory)

                dump(fname,None,targetDirectory)


#read cat file
cat=dict()
catPath=os.path.join(gameDirectory,r"Data\cas.cat") #Seems to always be in the same place
if os.path.isfile(catPath):
    print("Reading cat entries...")
    readCat(cat,catPath)

    # Check if there's a patched version.
    patchedCat=os.path.join(patchDirectory,os.path.relpath(catPath,gameDirectory))
    if os.path.isfile(patchedCat):
        print("Reading patched cat entries...")
        readCat(cat,patchedCat)

if os.path.isdir(updateDirectory):
    #First, extract all expansion packs.
    for dir in os.listdir(updateDirectory):
        if not dir.startswith("Xpack"):
            continue

        print("Extracting expansion pack %s..." % dir)
        dumpRoot(os.path.join(updateDirectory,dir))

#Now extract the base game.
print("Extracting main game...")
dumpRoot(gameDirectory)
