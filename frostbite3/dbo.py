#This is essentially a binary JSON type container.
#Each entry can hold a value of a specic type or more entries embedded into it.
#Values are always little endian.
from struct import unpack
import io
from collections import OrderedDict

def unXor(path):
    """Take a filename (usually toc or cat), decrypt the file if necessary, close it and return the unencrypted data in a memory stream.

    As toc files are ~300 kB at most, make a memory stream even if the file wasn't encrypted in the first place (to get rid of the physical file handle)."""

    f=open(path,"rb")
    if path[-4:]==".toc":
        f=unXorMEA(f) #Detect and decrypt Mass Effect: Andromeda.

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

def unXorMEA(f):
    f.seek(0,2)
    size=f.tell()
    f.seek(-32,2)
    signature=f.read(32)
    if signature!=b"@e!adnXd$^!rfOsrDyIrI!xVgHeA!6Vc":
        f.seek(0)
        return f

    #Mass Effect: Andromeda uses custom encryption on TOC files.
    f.seek(-36,2)
    headerSize=unpackLE("I",f.read(4))[0]
    f.seek(0)
    encryptedData=f.read(size-headerSize)
    dataLen=len(encryptedData)
    data=bytearray(dataLen)
    key=encryptedData[0]
    for i in range(dataLen):
        data[i]=encryptedData[i]^key
        key=((encryptedData[0]^encryptedData[i])-(i%256))&0xFF

    f.close()
    return io.BytesIO(data)



def decode7bit(f):
    """Reads the next few bytes in a file as LEB128/7bit encoding and returns an integer"""
    result,shift = 0,0
    while 1:
        byte=f.read(1)[0]
        result|=(byte&0x7f)<<shift
        if byte>>7==0: return result
        shift+=7

def readNullTerminatedString(f):
    result=b""
    while 1:
        byte=f.read(1)
        if byte==b"\x00": break
        result+=byte

    return result.decode()

def unpackLE(typ,data): return unpack("<"+typ,data)
def unpackBE(typ,data): return unpack(">"+typ,data)

class Guid:
    def __init__(self,f,bigEndian):
        #The first 3 elements are native endian and the last one is big endian.
        unpacker=unpackBE if bigEndian else unpackLE
        data=f.read(16)
        num1,num2,num3=unpacker("IHH",data[0:8])
        num4=unpackBE("Q",data[8:16])[0]
        self.val=num1,num2,num3,num4
    def frombytes(data,bigEndian):
        #Hack to init Guid from memory data.
        f=io.BytesIO(data)
        return Guid(f,bigEndian)
    def __eq__(self,other):
        return self.val==other.val
    def __ne__(self,other):
        return self.val!=other.val
    def __hash__(self):
        return hash(self.val)

    def format(self):
        return "%08x-%04x-%04x-%04x-%012x" % (self.val[0],self.val[1],self.val[2],
                                             (self.val[3]>>48)&0xFFFF,self.val[3]&0x0000FFFFFFFFFFFF)
    def isNull(self):
        return self.val==(0,0,0,0)

class DbObjectId:
    def __init__(self,f):
        self.id=f.read(12)

class DbTimestamp:
    def __init__(self,f):
        self.timeData=f.read(8)

class DbRecordId:
    def __init__(self,f):
        self.extentId, self.pageId, self.slotId = unpackLE("HHH",f.read(6))

class Vector4D:
    def __init__(self,f):
        self.x, self.y, self.z, self.w = unpackLE("ffff",f.read(16))

class Matrix4x4:
    def __init__(self,f):
        self.vecs=list()
        for i in range(4):
            self.vecs.append(Vector4D(f))

class DbTimespan:
    def __init__(self,f):
        val=decode7bit(f)
        lower=(val&0x00000000FFFFFFFF)
        upper=(val&0xFFFFFFFF00000000)>>32
        flag=lower&1
        self.timeSpan=((lower>>1)^flag)|(((upper>>1)^flag)<<32)

class DbObjectType:
    Eoo = 0x0
    Array = 0x1
    Object = 0x2
    HomoArray = 0x3
    Null = 0x4
    ObjectId = 0x5
    Bool = 0x6
    String = 0x7
    Integer = 0x8
    Long = 0x9
    VarInt = 0xA
    Float = 0xB
    Double = 0xC
    Timestamp = 0xD
    RecordId = 0xE
    GUID = 0xF
    SHA1 = 0x10
    Matrix44 = 0x11
    Vector4 = 0x12
    Blob = 0x13
    Attachment = 0x14
    Timespan = 0x15
    StringAtom = 0x16
    TypedBlob = 0x17
    Environment = 0x18
    InternalMin = 0x0
    InternalMax = 0x1F
    Mask = 0x1F
    TaggedField = 0x40
    Anonymous = 0x80

    def __init__(self):
        pass

class DbObject:
    def __init__(self,f,defaultVal=None): #read the data from file
        if not f:
            self.content=defaultVal
            return

        header=f.read(1)[0]
        self.typ=header&0x1F
        self.flags=header>>5
        if self.flags&0x04:
            #root entry
            self.name=""
        else:
            self.name=readNullTerminatedString(f)

        if self.typ==DbObjectType.Array:
            self.listLength=decode7bit(f) #self
            entries=list()
            endPos=f.tell()+self.listLength
            while f.tell()<endPos-1: #lists end on nullbyte
                entries.append(DbObject(f))
            self.content=entries
            if f.read(1)!=b"\x00": raise Exception(r"Array does not end with \x00 byte. Position: "+str(f.tell()))

        elif self.typ==DbObjectType.Object:
            self.elems=OrderedDict()
            entrySize=decode7bit(f)
            endPos=f.tell()+entrySize
            while f.tell()<endPos-1: #-1 because of final nullbyte
                content=DbObject(f)
                self.elems[content.name]=content
            if f.read(1)!=b"\x00": raise Exception(r"Entry does not end with \x00 byte. Position: "+str(f.tell()))

        elif self.typ==DbObjectType.Null:
            pass

        elif self.typ==DbObjectType.ObjectId:
            self.content=DbObjectId(f)

        elif self.typ==DbObjectType.Bool:
            self.content=unpackLE("?",f.read(1))[0]

        elif self.typ==DbObjectType.String:
            data=f.read(decode7bit(f)-1)
            self.content=data.decode()
            f.seek(1,1) #trailing null

        elif self.typ==DbObjectType.Integer:
            self.content=unpackLE("I",f.read(4))[0]

        elif self.typ==DbObjectType.Long:
            self.content=unpackLE("Q",f.read(8))[0]

        elif self.typ==DbObjectType.VarInt:
            val=decode7bit(f)
            self.content=(val>>1)^(val&1)

        elif self.typ==DbObjectType.Float:
            self.content=unpackLE("f",f.read(4))[0]

        elif self.typ==DbObjectType.Double:
            self.content=unpackLE("d",f.read(8))[0]

        elif self.typ==DbObjectType.Timestamp:
            self.content=DbTimestamp(f)

        elif self.typ==DbObjectType.RecordId:
            self.content=DbRecordId(f)

        elif self.typ==DbObjectType.GUID:
            self.content=Guid(f,False)

        elif self.typ==DbObjectType.SHA1:
            self.content=f.read(20)

        elif self.typ==DbObjectType.Vector4:
            self.content=Vector4D(f)

        elif self.typ==DbObjectType.Matrix44:
            self.content=Matrix4x4(f)

        elif self.typ==DbObjectType.Blob:
            self.content=f.read(decode7bit(f))

        elif self.typ==DbObjectType.Attachment:
            self.content=f.read(20) #SHA1

        elif self.typ==DbObjectType.Timespan:
            self.content=DbTimespan(f)

        else:
            raise Exception("Unhandled DB object type 0x%02x at 0x%08x." % (self.typ,f.tell()))

    def get(self,fieldName,defaultVal=None):
        try: return self.elems[fieldName].content
        except: return defaultVal

    def getSubObject(self,fieldName):
        try: return self.elems[fieldName]
        except: return None

def readToc(tocPath): #take a filename, decrypt the file and make an entry out of it
    return DbObject(unXor(tocPath))
