#Non-cas bundles are handled here.
#Unlike toc files these are always big endian.
from struct import unpack,pack
import dbo

def readNullTerminatedString(f):
    result=b""
    while 1:
        byte=f.read(1)
        if byte==b"\x00": break
        result+=byte

    return result.decode()

def alignValue(val,block):
    tmp=val%block
    if tmp==0: return val
    return val+block-tmp

class Bundle:
    def __init__(self, f): 
        metaSize=unpack(">I",f.read(4))[0] #size of the meta section/offset of the payload section
        metaStart=f.tell()
        metaEnd=metaStart+metaSize
        self.header=Header(unpack(">8I",f.read(32)),metaStart)
        if self.header.magic!=0x970d1c13: raise Exception("Wrong noncas bundle header magic.")
        self.sha1List=[f.read(20) for i in range(self.header.numEntry)] #one sha1 for each ebx+res+chunk
        self.ebxEntries=[BundleEntry(unpack(">3I",f.read(12))) for i in range(self.header.numEbx)]
        self.resEntries=[BundleEntry(unpack(">3I",f.read(12))) for i in range(self.header.numRes)]
        #ebx are done, but res have extra content
        for entry in self.resEntries:
            entry.resType=unpack(">I",f.read(4))[0] #FNV-1 hash of resource type's name
        for entry in self.resEntries:
            entry.resMeta=f.read(16) #often 16 nulls (always null for textures)

        self.chunkEntries=[Chunk(f) for i in range(self.header.numChunks)]

        
        #chunkmeta section, uses sbtoc structure, defines h32 and meta. If meta != nullbyte, then the corresponding chunk should have range entries.
        #Then again, noncas is crazy so this is only true for cas. There is one chunkMeta element (consisting of h32 and meta) for every chunk.
        #h32 is the FNV-1 hash applied to a string. For some audio files for example, the files are accessed via ebx files which of course have a name.
        #The hash of this name in lowercase is the h32 found in the chunkMeta. The same hash is also found in the ebx file itself at the keyword NameHash
        #For textures, the h32 is found in the corresponding res file. The res file also contains a name and once again the hash of this name is the h32.
        #meta for textures usually contains firstMip 0/1/2.
        if self.header.numChunks>0: self.chunkMeta=dbo.DbObject(f)
        for i in range(self.header.numChunks):
            self.chunkEntries[i].meta=self.chunkMeta.content[i].getSubObject("meta")
            self.chunkEntries[i].h32=self.chunkMeta.content[i].get("h32")
        
        for entry in self.ebxEntries + self.resEntries: #ebx and res have a path and not just a guid
            f.seek(self.header.offsetString+entry.offsetString)
            entry.name=readNullTerminatedString(f)

        f.seek(metaEnd) #PAYLOAD. Just grab all the payload offsets and sizes and add them to the entries without actually reading the payload. Also attach sha1 to entry.
        sha1Counter=0
        for entry in self.ebxEntries+self.resEntries+self.chunkEntries:
            entry.offset=alignValue(f.tell(),16)
            f.seek(entry.offset+entry.size)
            entry.sha1=self.sha1List[sha1Counter]
            sha1Counter+=1



    
class Header: #8 uint32
    def __init__(self,values,metaStart):
        self.magic           =values[0] #970d1c13 for unpatched files
        self.numEntry        =values[1] #total entries = numEbx + numRes + numChunks
        self.numEbx          =values[2]
        self.numRes          =values[3]
        self.numChunks       =values[4]
        self.offsetString    =values[5] +metaStart #offsets start at the beginning of the header, thus +metaStart
        self.offsetChunkMeta =values[6] +metaStart #redundant
        self.sizeChunkMeta   =values[7] #redundant

class BundleEntry: #3 uint32 + 1 string
    def __init__(self,values):
        self.offsetString=values[0] #in the name strings section
        self.size=values[1] #total size of the payload (for zlib including the two ints before the zlib)
        self.originalSize=values[2] #uncompressed size (for zlib after decompression and ignoring the two ints)
        #note: for zlib the uncompressed size is saved in both the file and the archive
        #      for zlib the compressed size in the file is the (size in the archive)-8


class Chunk:
    def __init__(self, f):
        self.id=dbo.Guid(f,True)
        self.rangeStart=unpack(">I",f.read(4))[0]
        self.rangeEnd=unpack(">I",f.read(4))[0] #total size of the payload is rangeEnd-rangeStart
        self.logicalOffset=unpack(">I",f.read(4))[0]
        self.size=self.rangeEnd-self.rangeStart
        #rangeStart, rangeEnd and logicalOffset are for textures. Non-texture chunks have rangeStart=logicalOffset=0 and rangeEnd being the size of the payload.
        #For cas bundles: rangeEnd is always exactly the size of compressed payload (which is specified too).
        #Furthermore for cas, rangeStart defines the point at which the mipmap number specified by chunkMeta::meta is reached in the compressed payload.
        #logicalOffset then is the uncompressed equivalent of rangeStart.
        #However for noncas, rangeStart and rangeEnd work in absolutely crazy ways. Their individual values easily exceed the actual size of the file.
        #Adding the same number to both of them does NOT cause the game to crash when loading, so really only the difference matters.
        #Additionally the sha1 for these texture chunks does not match the payload. The non-texture chunks that come AFTER such a chunk have the correct sha1 again.
