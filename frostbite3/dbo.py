#This is essentially a binary JSON type container.
#Each entry can hold a value of a specic type or more entries embedded into it.
#Values are always little endian.
from struct import unpack
import io
from collections import OrderedDict

def read128(f):
    """Reads the next few bytes in a file as LEB128/7bit encoding and returns an integer"""
    result,i = 0,0
    while 1:
        byte=f.read(1)[0]
        result|=(byte&127)<<i
        if byte>>7==0: return result
        i+=7

def readNullTerminatedString(f):
    result=b""
    while 1:
        byte=f.read(1)
        if byte==b"\x00": break
        result+=byte

    return result.decode()

def unXor(path):
    """Take a filename (usually toc or cat), decrypt the file if necessary, close it and return the unencrypted data in a memory stream.

    As toc files are ~300 kB at most, make a memory stream even if the file wasn't encrypted in the first place (to get rid of the physical file handle)."""
    
    f=open(path,"rb")
    magic=f.read(4)
    if magic in (b"\x00\xD1\xCE\x00"): #the file is XOR encrypted and has a signature
        f.seek(296) #skip the signature
        key=[f.read(1)[0]^0x7b for i in range(260)] #bytes 257 258 259 are not used
        encryptedData=f.read()
        size=len(encryptedData)
        data=bytearray(size) #initalize the buffer
        for i in range(size):
            data[i]=key[i%257]^encryptedData[i]
    elif magic in (b"\x00\xD1\xCE\x01",b"\x00\xD1\xCE\x03"): #the file has a signature, but an empty key; it's not encrypted
        f.seek(556) #skip signature + skip empty key
        data=f.read()
    else: #the file is not encrypted; no key + no signature
        f.seek(0)
        data=f.read()
    f.close()

    return io.BytesIO(data)

class DbObject:
    def __init__(self,toc,defVal=None): #read the data from file
        if not toc:
            self.content=defVal
            return

        header=toc.read(1)[0]
        self.typ=header&0x1F
        self.flags=header>>5
        if self.flags&0x04:
            #root entry
            self.name=""
        else:
            self.name=readNullTerminatedString(toc)
        
        if   self.typ==0x0f: self.content=toc.read(16) #guid
        elif self.typ==0x09: self.content=unpack("Q",toc.read(8))[0] #64-bit integer
        elif self.typ==0x08: self.content=unpack("I",toc.read(4))[0] #32-bit integer
        elif self.typ==0x06: self.content=True if toc.read(1)==b"\x01" else False #boolean
        elif self.typ==0x02: #entry containing fields
            self.elems=OrderedDict()
            entrySize=read128(toc)
            endPos=toc.tell()+entrySize
            while toc.tell()<endPos-1: #-1 because of final nullbyte
                content=DbObject(toc)
                self.elems[content.name]=content
            if toc.read(1)!=b"\x00": raise Exception(r"Entry does not end with \x00 byte. Position: "+str(toc.tell()))
        elif self.typ==0x13: self.content=toc.read(read128(toc)) #blob
        elif self.typ==0x10: self.content=toc.read(20) #sha1
        elif self.typ==0x07: #string, length prefixed as 7bit int.
            data=toc.read(read128(toc)-1)
            self.content=data.decode()
            toc.seek(1,1) #trailing null
        elif self.typ==0x01: #list
            self.listLength=read128(toc) #self
            entries=list()
            endPos=toc.tell()+self.listLength
            while toc.tell()<endPos-1: #lists end on nullbyte
                entries.append(DbObject(toc))
            self.content=entries
            if toc.read(1)!=b"\x00": raise Exception(r"List does not end with \x00 byte. Position: "+str(toc.tell()))
        else: raise Exception("Unknown type: "+hex(self.typ)+" "+hex(toc.tell()))

    def get(self,fieldName):
        try: return self.elems[fieldName].content
        except: return None

    def getSubEntry(self,fieldName):
        try: return self.elems[fieldName]
        except: return None

    def set(self,fieldName,val):
        self.elems[fieldName]=DbObject(None,val)

    def writeKeyValues(self,f,lvl=0,name=""):
        if not self.flags&0x04:
            f.write(lvl*"\t"+self.name)
        else:
            f.write(lvl*"\t"+name)

        if   self.typ==0x0f: f.write("\t"+self.content.hex())
        elif self.typ==0x09: f.write("\t"+str(self.content))
        elif self.typ==0x08: f.write("\t"+str(self.content))
        elif self.typ==0x06: f.write("\t"+str(self.content))
        elif self.typ==0x02:
            f.write("\n"+lvl*"\t"+"{\n")
            for entry in self.elems:
                self.elems[entry].writeKeyValues(f,lvl+1)
            f.write(lvl*"\t"+"}")
        elif self.typ==0x13: f.write("\t"+self.content.hex())
        elif self.typ==0x10: f.write("\t"+self.content.hex())
        elif self.typ==0x07: f.write("\t"+self.content)
        elif self.typ==0x01:
            f.write("\n"+lvl*"\t"+"{\n")
            for i in range(len(self.content)):
                self.content[i].writeKeyValues(f,lvl+1,str(i))
            f.write(lvl*"\t"+"}")

        f.write("\n")

def readToc(tocPath): #take a filename, decrypt the file and make an entry out of it
    return DbObject(unXor(tocPath))
