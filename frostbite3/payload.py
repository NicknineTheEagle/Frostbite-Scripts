import cas
import os
import io
from struct import pack,unpack
import ctypes
import zlib

liblz4 = ctypes.cdll.LoadLibrary(r"..\thirdparty\liblz4")
libzstd = ctypes.cdll.LoadLibrary(r"..\thirdparty\libzstd")
try: oodle = ctypes.windll.LoadLibrary(r"..\thirdparty\oo2core_4_win64")
except: oodle = None

libzstd.ZSTD_createDDict.restype=ctypes.c_void_p
libzstd.ZSTD_createDDict.argtypes=[ctypes.c_void_p,ctypes.c_size_t]
libzstd.ZSTD_freeDDict.argtypes=[ctypes.c_void_p]
libzstd.ZSTD_createDCtx.restype=ctypes.c_void_p
libzstd.ZSTD_decompress_usingDDict.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p]
libzstd.ZSTD_freeDCtx.argtypes=[ctypes.c_void_p]
libzstd.ZSTD_decompress.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t]
liblz4.LZ4_decompress_safe_partial.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int32,ctypes.c_int32,ctypes.c_int32]



def makeLongDirs(path):
    folderPath=lp(os.path.dirname(path))
    if not os.path.isdir(folderPath): os.makedirs(folderPath)

def open2(path,mode):
    #create folders if necessary and return the file handle
    if mode.find("w")!=-1: makeLongDirs(path)
    return open(lp(path),mode)

def lp(path): #long pathnames
    if path[:4]=='\\\\?\\' or path=="" or len(path)<=247: return path
    return '\\\\?\\' + os.path.normpath(path)



def readBlockHeader(f):
    #Block header is a bitfield:
    #8 bits: custom dict flag
    #24 bits: uncompressed size
    #8 bits: compression type
    #4 bits: always 7?
    #20 bits: compressed size
    num1, num2 = unpack(">II",f.read(8))
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
        if not oodle: raise Exception("You need oo2core_4_win64.dll to decompress Oodle v4.")
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
    f2=open2(outPath,"wb")

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
    f2=open2(outPath,"wb")

    instructionType=midInstructionType
    instructionSize=midInstructionSize

    #This is where magic happens: we need to splice bits from delta bundle and base bundle.
    #See here for details: https://pastebin.com/TftZEU9q
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
            raise Exception("Unknown payload type: 0x%02x Delta offset: 0x%08x" % (instructionType,delta.tell()-4))

        instructionType=-1
        if f2.tell()==originalSize: break

    #May need to get the rest from the base bundle (infinite type 0 instructions).
    while f2.tell()!=originalSize:
        decompressBlock(base,f2)

    base.close()
    delta.close()
    f2.close()

#for each bundle, the dump script selects one of these six functions
def casPayload(bundleEntry, targetPath):
    if os.path.isfile(lp(targetPath)): return False

    #Some files may be from localizations user doesn't have installed.
    try:
        catEntry=cas.catDict[bundleEntry.get("sha1")]
        decompressPayload(catEntry.path,catEntry.offset,catEntry.size,bundleEntry.get("originalSize"),targetPath)
        return True
    except:
        return False

def casPatchedPayload(bundleEntry, targetPath):
    if os.path.isfile(lp(targetPath)): return False

    if bundleEntry.get("casPatchType")==2:
        catDelta=cas.catDict[bundleEntry.get("deltaSha1")]
        catBase=cas.catDict[bundleEntry.get("baseSha1")]
        decompressPatchedPayload(catBase.path,catBase.offset,
                                 catDelta.path,catDelta.offset,catDelta.size,
                                 bundleEntry.get("originalSize"),targetPath)
        return True
    else:
        return casPayload(bundleEntry, targetPath) #if casPatchType is not 2, use the unpatched function.

def casChunkPayload(entry,targetPath):
    if os.path.isfile(lp(targetPath)): return False

    #Some files may be from localizations user doesn't have installed.
    try:
        catEntry=cas.catDict[entry.get("sha1")]
        decompressPayload(catEntry.path,catEntry.offset,catEntry.size,None,targetPath)
        return True
    except:
        return False

def noncasPayload(entry, targetPath, sourcePath):
    if os.path.isfile(lp(targetPath)): return False
    decompressPayload(sourcePath,entry.offset,entry.size,entry.originalSize,targetPath)
    return True

def noncasPatchedPayload(entry, targetPath, sourcePath):
    if os.path.isfile(lp(targetPath)): return False
    decompressPatchedPayload(sourcePath[0], entry.baseOffset,#entry.baseSize,
                            sourcePath[1], entry.deltaOffset, entry.deltaSize,
                            entry.originalSize, targetPath,
                            entry.midInstructionType, entry.midInstructionSize)
    return True

def noncasChunkPayload(entry, targetPath, sourcePath):
    if os.path.isfile(lp(targetPath)): return False
    decompressPayload(sourcePath,entry.get("offset"),entry.get("size"),None,targetPath)
    return True



def zstdInit():
    #Load Zstd compression dictionary.
    global zstd_dict

    f=open("zstdDict.bin","rb")
    data=f.read()
    f.close()
    zstd_dict=ctypes.c_void_p(libzstd.ZSTD_createDDict(data,len(data)))

def zstdCleanup():
    libzstd.ZSTD_freeDDict(zstd_dict)
