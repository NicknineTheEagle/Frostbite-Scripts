#Need for Speed: Edge stuff is handled here.
import dbo
import cas
import payload
import ebx
import io
import os
from struct import pack,unpack
import res

def readStringBuffer(f,len):
    result=b""
    end=f.tell()+len

    result=b""
    while 1:
        byte=f.read(1)
        if byte==b"\x00": break
        result+=byte

    f.seek(end)
    return result.decode()

#Mutated cas.cat format.
class DalEntry:
    def __init__(self,f,offset,dasPath):
        self.offset=offset
        self.size=unpack("<I",f.read(4))[0]
        self.path=dasPath

def readDal(dalPath):
    dasDirectory=os.path.dirname(dalPath)
    f=open(dalPath,"rb")
    numDas=unpack("<B",f.read(1))[0]

    for i in range(numDas):
        name=readStringBuffer(f,64)
        numEntries=unpack("<I",f.read(4))[0]
        dasPath=os.path.join(dasDirectory,"das_%s.das" % name)

        f2=open(dasPath,"rb")
        dataOffset=numEntries*24
        for j in range(numEntries):
            sha1=f2.read(20)
            dalEntry=DalEntry(f2,dataOffset,dasPath)
            cas.catDict[sha1]=dalEntry
            dataOffset+=dalEntry.size

        f2.close()

    f.close()

def prepareDir(targetPath):
    if os.path.exists(targetPath): return True
    folderPath=os.path.dirname(targetPath)
    os.makedirs(folderPath,exist_ok=True)
    #print(targetPath)

def dump(tocPath,outPath):
    toc=dbo.readToc(tocPath)
    if not (toc.getSubObject("bundles") or toc.get("chunks")): return #there's nothing to extract (the sb might not even exist)

    sbPath=tocPath[:-3]+"sb"
    sb=open(sbPath,"rb")

    chunkPathToc=os.path.join(outPath,"chunks")
    bundlePath=os.path.join(outPath,"bundles")
    ebxPath=os.path.join(bundlePath,"ebx")
    resPath=os.path.join(bundlePath,"res")
    chunkPath=os.path.join(bundlePath,"chunks")

    if not toc.get("das"): raise Exception("Non-DAS superbundle found in NFS: Edge.")

    bundles=toc.getSubObject("bundles") #names offsets sizes (list sizes should be same)
    offsets=bundles.get("offsets")

    for offset in offsets:
        sb.seek(offset.content)
        bundle=dbo.DbObject(sb)

        for entry in bundle.get("ebx",list()): #name sha1 size originalSize
            path=os.path.join(ebxPath,entry.get("name")+".ebx")
            if payload.casBundlePayload(entry,path,False):
                ebx.addEbxGuid(path,ebxPath)

        for entry in bundle.get("res",list()): #name sha1 size originalSize resRid resType resMeta
            res.addToResTable(entry.get("resRid"),entry.get("name"),entry.get("resType"),entry.get("resMeta"))
            path=os.path.join(resPath,entry.get("name")+res.getResExt(entry.get("resType")))
            payload.casBundlePayload(entry,path,False)

        for entry in bundle.get("chunks",list()): #id sha1 size logicalOffset logicalSize chunkMeta::meta
            path=os.path.join(chunkPath,entry.get("id").format()+".chunk")
            payload.casBundlePayload(entry,path,True)

    #Deal with the chunks which are defined directly in the toc.
    #These chunks do NOT know their originalSize.
    for entry in toc.get("chunks"): #id sha1
        targetPath=os.path.join(chunkPathToc,entry.get("id").format()+".chunk")
        payload.casChunkPayload(entry,targetPath)

    sb.close()

#FrontEnd DAS files, this is its own archive format completely separate from the rest of the filesystem.
def extractDas(dasPath,outPath):
    f=open(dasPath,"rb")
    feFolder=os.path.join(outPath,"fe")

    #Decrypt DAS header
    magic=f.read(4)
    if magic in (b"\x00\xD1\xCE\x00",b"\x00\xD1\xCE\x01"): #the file is XOR encrypted and has a signature
        f.seek(296) #skip the signature
        key=[f.read(1)[0]^0x7b for i in range(260)] #bytes 257 258 259 are not used
        numEntries=unpack("<I",f.read(4))[0]
        size=numEntries*132
        encryptedData=f.read(size)
        data=bytearray(size) #initalize the buffer
        for i in range(size):
            data[i]=key[i%257]^encryptedData[i]
    elif magic in (b"\x00\xD1\xCE\x03"): #the file has empty signature and empty key, it's not encrypted
        f.seek(556) #skip signature + skip empty key
        numEntries=unpack("<I",f.read(4))[0]
        size=numEntries*132
        encryptedData=f.read(size)
        data=bytearray(size) #initalize the buffer
        for i in range(size):
            data[i]=encryptedData[i]^0x7b
    else:
        raise Exception("Unknown DAS header magic.")

    encryptionMode=magic[3]
    header=io.BytesIO(data)

    for i in range(numEntries):
        name=readStringBuffer(header,128)
        size=unpack("<I",header.read(4))[0]

        if encryptionMode==0:
            encryptedData=f.read(size)
            data=bytearray(size)
            for i in range(size):
                data[i]=key[i%257]^encryptedData[i]
        elif encryptionMode==1:
            f.seek(292,1) #skip the signature
            encryptedData=f.read(size)
            data=bytearray(size)
            for i in range(size):
                data[i]=key[i%257]^encryptedData[i]
        else:
            data=f.read(size)

        targetFile=os.path.normpath(os.path.join(feFolder,name))
        prepareDir(targetFile)
        f2=open(targetFile,"wb")
        f2.write(data)
        f2.close()

    f.close()

def dumpRoot(dataDir,outPath):
    for dir0, dirs, ff in os.walk(dataDir):
        for fname in ff:
            if fname[-4:]==".toc":
                fname=os.path.join(dir0,fname)
                localPath=os.path.relpath(fname,dataDir)
                print(localPath)
                dump(fname,outPath)

def dumpFE(dataDir,outPath):
    for fname in os.listdir(dataDir):
        if fname[:6]=="das_fe":
            fname=os.path.join(dataDir,fname)
            localPath=os.path.relpath(fname,dataDir)
            print(localPath)
            extractDas(fname,outPath)
