#Non-cas bundles are handled here.
#Unlike toc files these are always big endian.
from struct import unpack,pack
import io
import dbo

def readNullTerminatedString(f):
    result=b""
    while 1:
        byte=f.read(1)
        if byte==b"\x00": break
        result+=byte

    return result.decode()

def seekPayloadBlock(f):
    num1, num2 = unpack(">II",f.read(8))
    uncompressedSize=num1&0x00FFFFFF
    comType=(num2&0xFF000000)>>24
    compressedSize=num2&0x000FFFFF
    if comType not in (0x00,0x02,0x09,0x0f,0x15): raise Exception("Unknown compression type 0x%02x at 0x%08x in %s" % (comType,f.tell()-8,f.name))
    f.seek(compressedSize,1)
    return uncompressedSize

def unpatchedBundle(base):
    """Read unpatched noncas bundle. Assign offset and size to each bundle entry. Return the bundle.

    Each entry has at least offset, size, originalSize."""
    
    b=Bundle(base)
    #obtain size and offset for each entry using the (known) originalSize  
    for entry in b.entries:
        entry.offset=base.tell()
        currentSize=0
        while currentSize!=entry.originalSize:
            currentSize+=seekPayloadBlock(base)
        entry.size=base.tell()-entry.offset
    return b

def yieldEntry(bundle, base, delta):
    """Hand a new entry over to the patcher function whenever the previous entry has its payload filled up, i.e.: currentSize == originalSize"""
    for entry in bundle.entries:    
        entry.baseOffset=base.tell()
        entry.deltaOffset=delta.tell()
        entry.currentSize=0 #fill this up until it equals originalSize.

        #An entry may be swapped during delta instructions of type 0 and 3:
        #type 0, while adding base blocks only
        #type 3, while adding delta blocks only
        #So the entry needs to know if it's in the middle of such an instruction, how many blocks to read, and which type.
        #Does the entry also need to know if it ends in the middle of an instruction? Not if the dll stops as soon originalSize is reached.
        entry.midInstructionSize=0
        entry.midInstructionType=-1 #Use -1 if it did not end in the middle of an instruction, else use the number of the type, i.e. 0 or 3.
        
        yield entry
        entry.baseSize=base.tell()-entry.baseOffset
        entry.deltaSize=delta.tell()-entry.deltaOffset

    #Add a fake entry. This entry not part of bundle.entries and thus not returned by the patcher function (good).
    #Advantages:
    #   1) Can move on to the next entry without having to make checks that it isn't the last entry (while avoiding try-except, which would just silently return even when there are legitimate bugs).
    #   2) Without it, the last entry would not have its baseSize and deltaSize calculated unless there's a for loop at the end. 
    fakeEntry=Stub()
    fakeEntry.currentSize=0 #add these two fields so it requests 0 payload
    fakeEntry.originalSize=0
    yield fakeEntry

class Stub: pass

def split1v7(num): return (num>>28,num&0x0fffffff) #0x7A945CF1 => (7, 0xA945CF1)

def patchedBundle(base, delta):
    """Take a file handle from a delta and a base bundle. Use the delta to patch the base and return bundle containing ebx/res/chunk entries.

   Each entry has at least
        originalSize (uncompressed size of the payload)
        baseOffset
        baseSize (compressed size)
        deltaOffset
        deltaSize (compressed size)
        midInstructionSize (the remaining number of iterations when a file starts in the middle of an instruction of type 0 or 3)
        midInstructionType (0 or 3 if a file starts in the middle of a corresponding instruction, else -1)
    which (together with the delta and base file paths) are exactly what's necessary to retrieve, decompress and patch the payload."""
    
    #The function does two things:
    #    1) Use the delta file to patch the metadata section of the base file, then create entries from the patched metadata.
    #    2) Next, go through the payload-related instructions of the delta file, and calculate offsets and (compressed) sizes for each entry.
    
    #the delta file is split in three parts: The first 16 bytes are header, then there's a section to patch the base metadata and then one for the base payload
    deltaOffset=delta.tell()
    magic = delta.read(8)
    if magic!=b"\0\0\0\x01\0\0\0\0": raise Exception("Wrong non-CAS delta bundle magic")
    deltaMetaSize, deltaPayloadSize = unpack(">II",delta.read(8))
    #make some calculations for later on
    deltaPayloadOffset=deltaOffset+16+deltaMetaSize #16 is the size of the header
    deltaEof=deltaPayloadOffset+deltaPayloadSize #to break the payload loop later on

    #METADATA SECTION
    patchMetaSize=unpack(">I",delta.read(4))[0] #patch refers to the base after applying the delta
    baseMetaSize=unpack(">I",base.read(4))[0] #not used
    baseOffset=base.tell()

    #patch the metadata in memory
    patchStream=io.BytesIO()
    patchStream.write(pack(">I",patchMetaSize))
    
    while delta.tell()<deltaPayloadOffset:
        instructionType, instructionSize = split1v7(unpack(">I",delta.read(4))[0])
        if   instructionType==0: patchStream.write(base.read(instructionSize)) #add base bytes
        elif instructionType==4: base.seek(instructionSize,1) #skip base bytes
        elif instructionType==8: patchStream.write(delta.read(instructionSize)) #add delta bytes
        else: print("Unknown meta type",instructionType, bad)
    #the metadata is patched, now read it in to get the entries
    patchStream.seek(0)
    b=Bundle(patchStream)
    base.seek(baseOffset+baseMetaSize) #go to the base payload section

    #whenever one entry has its payload filled up, use this to get the next entry
    getEntry=yieldEntry(b, base, delta) 
    entry=getEntry.__next__() #start with the first entry

    #PAYLOAD SECTION
    #Seek through the payload to assign a size and offset to each entry. The actual patching is done with the dll (although the following comments suggest otherwise).
    #The instructions of the delta file may stop even though some entries still need payload assigned to them.
    #It is expected that in this case, an infinite instruction of type 0 is performed until all entries are satisfied (coincides with the base reaching its end).
    #Conversely, all payloads might be satisfied but the delta eof not reached yet. In this case the delta explicitly specifies an instruction of type 4 to skip the final base blocks.

    while delta.tell()!=deltaEof:
        instructionType, instructionSize = split1v7(unpack(">I",delta.read(4))[0])
        if instructionType==0: #add base blocks without modification
            for i in range(instructionSize):
                entry.currentSize+=seekPayloadBlock(base)
                if entry.currentSize==entry.originalSize:
                    entry=getEntry.__next__()
                    entry.midInstructionSize=instructionSize-i-1 #remaining iterations
                    entry.midInstructionType=instructionType  
        elif instructionType==2: #make tiny fixes in the base block
            seekPayloadBlock(base)
            entry.currentSize+=unpack(">H",delta.read(2))[0]+1
            delta.seek(instructionSize,1)
            if entry.currentSize==entry.originalSize: entry=getEntry.__next__()
        elif instructionType==1: #make larger fixes in the base block
            baseBlock=seekPayloadBlock(base)
            prevOffset=0
            for i in range(instructionSize):
                targetOffset, skipSize = unpack(">HH",delta.read(4))
                entry.currentSize+=targetOffset-prevOffset
                entry.currentSize+=seekPayloadBlock(delta)
                prevOffset=targetOffset+skipSize
                if entry.currentSize==entry.originalSize: #this might be extremely bad, UNLESS the the instruction does not want to read more bytes after that anyway
                    if i!=instructionSize-1: bad #should be the last instruction
                    if baseBlock-prevOffset!=0: bad #there should be no bytes left to read
            entry.currentSize+=baseBlock-prevOffset
            if entry.currentSize==entry.originalSize: entry=getEntry.__next__()
        elif instructionType==3: #add delta blocks directly to the payload
            for i in range(instructionSize):
                entry.currentSize+=seekPayloadBlock(delta)
                if entry.currentSize==entry.originalSize:
                    entry=getEntry.__next__()
                    entry.midInstructionSize=instructionSize-i-1 #remaining iterations
                    entry.midInstructionType=instructionType
        elif instructionType==4: #skip entire blocks, do not increase currentSize at all
            for i in range(instructionSize):
                seekPayloadBlock(base)
        else:
            raise Exception("Unknown payload type: 0x%02x Delta offset: 0x%08x" % (instructionType,delta.tell()))
    
    #The delta is fully read, but it's not over yet.
    #Read remaining base blocks until all entries are satisfied (infinite instruction of type 0).
        
    #the current entry probably hasn't reached its full size yet and requires manual attention
    while entry.currentSize!=entry.originalSize:
        entry.currentSize+=seekPayloadBlock(base)

    #all remaining entries go here
    for entry in getEntry:
        while entry.currentSize!=entry.originalSize:
            entry.currentSize+=seekPayloadBlock(base)

    return b

class Bundle: #noncas, read metadata only and seek to the start of the payload section
    def __init__(self, f):
        metaSize=unpack(">I",f.read(4))[0]
        metaOffset=f.tell()
        self.header=Header(unpack(">8I",f.read(32)))
        if self.header.magic!=0x9D798ED5: raise Exception("Wrong noncas bundle header magic.")
        sha1List=[f.read(20) for i in range(self.header.totalCount)] #one sha1 for each ebx+res+chunk. Not necessary for extraction
        self.ebx=[BundleEntry(unpack(">2I",f.read(8))) for i in range(self.header.ebxCount)]
        self.res=[BundleEntry(unpack(">2I",f.read(8))) for i in range(self.header.resCount)]

        #ebx are done, but res have extra content
        for entry in self.res: entry.resType=unpack(">I",f.read(4))[0] #FNV-1 hash of resource type's name
        for entry in self.res: entry.resMeta=f.read(16) #often 16 nulls (always null for textures)
        for entry in self.res: entry.resRid=unpack(">Q",f.read(8))[0] #ebx use these to import res (bf3 used names)

        #chunks
        self.chunks=[Chunk(f) for i in range(self.header.chunkCount)]

        #chunkMeta. There is one chunkMeta entry for every chunk (i.e. self.chunks and self.chunkMeta both have the same number of elements).
        if self.header.chunkCount>0: self.chunkMeta=dbo.DbObject(f)
        for i in range(self.header.chunkCount):
            self.chunks[i].meta=self.chunkMeta.content[i].getSubObject("meta")
            self.chunks[i].h32=self.chunkMeta.content[i].get("h32")

        #ebx and res have a filename (chunks only have a 16 byte id)
        absStringOffset=metaOffset+self.header.stringOffset
        for entry in self.ebx+self.res: 
            f.seek(absStringOffset+entry.nameOffset)
            entry.name=readNullTerminatedString(f)
            
        self.entries=self.ebx+self.res+self.chunks
        f.seek(metaOffset+metaSize) #go to the start of the payload section
##        #optional: attach sha1s to entries
##        for i in range(len(self.entries)):
##            self.entries[i].sha1=sha1List[i]
    
class Header: #8 uint32
    def __init__(self,values):
        self.magic           =values[0] #970d1c13 for bf3, 9D798ED5 for bf4; but this version only supports bf4
        self.totalCount      =values[1] #total entries = ebx + res + chunks
        self.ebxCount        =values[2]
        self.resCount        =values[3]
        self.chunkCount      =values[4]
        self.stringOffset    =values[5] #offset of string section, relative to metadata start (i.e. 4 bytes into the file)
        self.chunkMetaOffset =values[6] #redundant
        self.chunkMetaSize   =values[7] #redundant
class BundleEntry: #ebx, res
    def __init__(self,values):
        self.nameOffset=values[0] #relative to the string section
        self.originalSize=values[1] #uncompressed size of the payload
class Chunk:
    def __init__(self, f):
        self.id=dbo.Guid(f,True)
        self.rangeStart, self.logicalSize, self.logicalOffset=unpack(">HHI",f.read(8)) #not sure if rangeStart is the correct name. The order might be wrong too.
        self.originalSize=self.logicalSize+self.logicalOffset #I know this equation from the (more verbose) cas bundles
