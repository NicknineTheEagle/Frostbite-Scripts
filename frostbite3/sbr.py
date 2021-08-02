#Harmony Sample Bank (SBR) format is parsed here. Used by NewWaveAsset to store info about variations and segments.
#SBR files are machine endian.
from struct import unpack,pack
import io
import dbo

def unpackLE(typ,data): return unpack("<"+typ,data)
def unpackBE(typ,data): return unpack(">"+typ,data)
def packLE(typ,data): return pack("<"+typ,data)
def packBE(typ,data): return pack(">"+typ,data)

def readInt8(obj,offset):
    obj.f.seek(offset)
    return obj.unpacker("B",obj.f.read(0x01))[0]

def readInt16(obj,offset):
    obj.f.seek(offset)
    return obj.unpacker("H",obj.f.read(0x02))[0]

def readInt32(obj,offset):
    obj.f.seek(offset)
    return obj.unpacker("I",obj.f.read(0x04))[0]

def readInt64(obj,offset):
    obj.f.seek(offset)
    return obj.unpacker("Q",obj.f.read(0x08))[0]

def hasher(keyword): #32bit FNV-1 hash with FNV_offset_basis = 5381 and FNV_prime = 33
    hash = 5381
    for byte in keyword:
        hash = (hash*33) ^ ord(byte)
        hash &= 0xffffffff # use & because Python promotes the num instead of intended overflow
    return hash

class FieldType:
    Boolean = 0x0
    Int32 = 0x1
    UInt32 = 0x2
    Int64 = 0x3
    UInt64 = 0x4
    Float32 = 0x5
    Float64 = 0x6
    String = 0x7
    Pointer = 0x8

    def __init__(self):
        pass

class Field:
    def __init__(self,dset,offset,dataOffset):
        self.f=dset.f
        self.unpacker=dset.unpacker
        self.packer=dset.packer
        self.dataOffset=dataOffset

        self.f.seek(offset)
        data=self.unpacker("IBBHQII",self.f.read(0x18))
        self.id=data[0]
        self.dataType=data[1]
        self.storeType=data[2]
        self.storeParam1=data[3]
        self.storeParam2=data[4]
        self.tableOffset=data[5]
        self.values=list()

        if self.storeType==0x00:
            #Same value for all elements.
            for i in range(dset.numElems):
                val=self.storeParam2
                self.saveValue(val)
        elif self.storeType==0x01:
            #Steady increment for each value.
            delta=self.storeParam1
            baseOffset=self.storeParam2
            if delta&0x8000: delta-=0x10000 #Signed value.

            for i in range(dset.numElems):
                val=baseOffset+delta*i
                self.saveValue(val)
        elif self.storeType==0x02:
            #Base offset + bit shifting.
            shift=self.storeParam1 & 0xFF
            valSize=(self.storeParam1 >> 8) & 0xFF
            baseOffset=self.storeParam2

            for i in range(dset.numElems):
                if valSize==0x01:
                    val=readInt8(self,self.tableOffset+valSize*i)
                elif valSize==0x02:
                    val=readInt16(self,self.tableOffset+valSize*i)
                elif valSize==0x04:
                    val=readInt32(self,self.tableOffset+valSize*i)
                elif valSize==0x08:
                    val=readInt64(self,self.tableOffset+valSize*i)

                val<<=shift
                val+=baseOffset
                self.saveValue(val)
        elif self.storeType==0x03:
            #Table of unique values with index pointers.
            idxBits=self.storeParam1 & 0xFF
            valSize=(self.storeParam1 >> 8) & 0xFF
            numValues=self.storeParam2
            idxOffset=self.tableOffset+numValues*valSize

            for i in range(dset.numElems):
                byte=readInt8(self,idxOffset+(i*idxBits) // 8)
                shift=(i*idxBits) % 8
                byte>>=shift
                idx=byte & ((1<<idxBits)-1)

                if valSize==0x01:
                    val=readInt8(self,self.tableOffset+valSize*idx)
                elif valSize==0x02:
                    val=readInt16(self,self.tableOffset+valSize*idx)
                elif valSize==0x04:
                    val=readInt32(self,self.tableOffset+valSize*idx)
                elif valSize==0x08:
                    val=readInt64(self,self.tableOffset+valSize*idx)

                self.saveValue(val)
        elif self.storeType==0x04:
            #Simple list of values.
            for i in range(dset.numElems):
                val=readInt64(self,self.tableOffset+0x08*i)
                self.saveValue(val)

    def saveValue(self,rawVal):
        #All values are stored internally as integers so now we must re-interpret them to the desired type.
        data=self.packer("Q",rawVal)

        if self.dataType==FieldType.Boolean:
            val=self.unpacker("?",data[:1])[0]
        elif self.dataType==FieldType.Int32:
            val=self.unpacker("i",data[:4])[0]
        elif self.dataType==FieldType.UInt32:
            val=self.unpacker("I",data[:4])[0]
        elif self.dataType==FieldType.Int64:
            val=self.unpacker("q",data[:8])[0]
        elif self.dataType==FieldType.UInt64:
            val=self.unpacker("Q",data[:8])[0]
        elif self.dataType==FieldType.Float32:
            val=self.unpacker("f",data[:4])[0]
        elif self.dataType==FieldType.Float64:
            val=self.unpacker("d",data[:8])[0]
        elif self.dataType==FieldType.String or self.dataType==FieldType.Pointer:
            val=self.unpacker("Q",data[:8])[0]

        self.values.append(val)

    def getString(self,elem):
        #For some reason, all pointers in NewWaveResource SBRs have 1 added to them.
        offset=self.dataOffset+self.values[elem]-1
        self.f.seek(offset)
        return dbo.readNullTerminatedString(self.f)

    def getGuid(self,elem):
        #Ditto.
        offset=self.dataOffset+self.values[elem]-1
        self.f.seek(offset)
        return dbo.Guid(self.f,self.unpacker==unpackBE)

class DataSet:
    def __init__(self,bank,offset):
        self.f=bank.f
        self.unpacker=bank.unpacker
        self.packer=bank.packer

        magic=readInt32(self,offset+0x00)
        if magic!=0x44534554: raise ValueError("Bad DSET header magic")

        self.id=readInt32(self,offset+0x08)
        self.dataOffset=readInt32(self,offset+0x18)
        self.numElems=readInt32(self,offset+0x38)
        self.numFields=readInt16(self,offset+0x3c)
        self.fields=dict()

        for i in range(self.numFields):
            field=Field(self,offset+0x48+0x18*i,self.dataOffset)
            self.fields[field.id]=field

    def get(self,name):
        #Field IDs can actually be whatever but NewWaveResource uses name hashes.
        id=hasher(name)
        if id in self.fields:
            return self.fields[id]

        return None

class Bank:
    def __init__(self,path):
        #Load the whole SBR into memory.
        f=open(path,"rb")
        self.f=io.BytesIO(f.read())
        f.close()

        magic=self.f.read(0x04)
        if magic==b"SBle":
            self.unpacker=unpackLE
            self.packer=packLE
        elif magic==b"SBbe":
            self.unpacker=unpackBE
            self.packer=packBE
        else:
            raise ValueError("Bad SBR header magic in: "+path)

        self.numDataSets=readInt16(self,0x0a)
        self.tableOffset=readInt32(self,0x18)
        self.dataOffset=readInt32(self,0x20)
        self.dataSets=dict()

        for i in range(self.numDataSets):
            dsetOffset=readInt32(self,self.tableOffset+i*0x08)
            dset=DataSet(self,dsetOffset)
            self.dataSets[dset.id]=dset

    def get(self,name):
        id=hasher(name)
        if id in self.dataSets:
            return self.dataSets[id]

        return None
