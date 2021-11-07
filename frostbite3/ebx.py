#Ebx format is the cornerstone of Frostbite, it's an asset node of sorts used to reference actual game assets
#stored in chunk and res files as well as define scripts and configs for the game.
#Ebx is machine endian.
import os
import copy
from struct import unpack,pack
import shutil
import pickle
from dbo import Guid
import res
import sbr

def unpackLE(typ,data): return unpack("<"+typ,data)
def unpackBE(typ,data): return unpack(">"+typ,data)

guidTable=dict()
parsedEbx=list()

def addEbxGuid(path,ebxRoot):
    if path in parsedEbx:
        return

    #Add EBX GUID and name to the database.
    #Only parse primary instance since we just need Name field and there are some enormous EBX files.
    dbx=Dbx(path,ebxRoot,True)
    guidTable[dbx.fileGUID]=dbx.trueFilename
    parsedEbx.append(path)

def writeGuidTable(dumpFolder):
    f=open(os.path.join(dumpFolder,"guidTable.bin"),"wb")
    pickle.dump(guidTable,f)
    f.close()

def loadGuidTable(dumpFolder):
    global guidTable
    path=os.path.join(dumpFolder,"guidTable.bin")
    if not os.path.isfile(path):
        print("WARNING: EBX GUID table is missing, it is required to properly parse links between different EBX files!")
        return

    f=open(path,"rb")
    guidTable=pickle.load(f)
    f.close()

def makeLongDirs(path):
    folderPath=lp(os.path.dirname(path))
    os.makedirs(folderPath,exist_ok=True)

def open2(path,mode):
    #create folders if necessary and return the file handle
    if "w" in mode:
        makeLongDirs(path)

    #make sure we write text files in UTF-8 since that's what string fields use
    if "b" not in mode:
        return open(lp(path),mode,encoding="utf-8")

    return open(lp(path),mode)

def lp(path): #long pathnames
    if path[:4]=='\\\\?\\' or path=="" or len(path)<=247: return path
    return '\\\\?\\' + os.path.normpath(path)

def hasher(keyword): #32bit FNV-1 hash with FNV_offset_basis = 5381 and FNV_prime = 33
    hash = 5381
    for byte in keyword:
        hash = (hash*33) ^ ord(byte)
        hash &= 0xffffffff # use & because Python promotes the num instead of intended overflow
    return hash
class Header:
    def __init__(self,varList):
        self.absStringOffset     = varList[0]  ## absolute offset for string section start
        self.lenStringToEOF      = varList[1]  ## length from string section start to EOF
        self.numGUID             = varList[2]  ## number of external GUIDs
        self.numInstanceRepeater = varList[3]  ## total number of instance repeaters
        self.numGUIDRepeater     = varList[4]  ## instance repeaters with GUID
        self.unknown             = varList[5]
        self.numComplex          = varList[6]  ## number of complex entries
        self.numField            = varList[7]  ## number of field entries
        self.lenName             = varList[8]  ## length of name section including padding
        self.lenString           = varList[9]  ## length of string section including padding
        self.numArrayRepeater    = varList[10]
        self.lenPayload          = varList[11] ## length of normal payload section; the start of the array payload section is absStringOffset+lenString+lenPayload
class FieldDescriptor:
    def __init__(self,varList,keywordDict,version):
        self.name            = keywordDict[varList[0]]
        self.type            = varList[1]
        self.ref             = varList[2] #the field may contain another complex
        self.offset          = varList[3] #offset in payload section; relative to the complex containing it
        self.secondaryOffset = varList[4]
        self.version         = version
        if self.name=="$": self.offset-=8

    def getFieldType(self):
        if self.version==1:
            return (self.type >> 4) & 0x1F
        else:
            return (self.type >> 5) & 0x1F
class ComplexDescriptor:
    def __init__(self,varList,keywordDict):
        self.name            = keywordDict[varList[0]]
        self.fieldStartIndex = varList[1] #the index of the first field belonging to the complex
        self.numField        = varList[2] #the total number of fields belonging to the complex
        self.alignment       = varList[3]
        self.type            = varList[4]
        self.size            = varList[5] #total length of the complex in the payload section
        self.secondarySize   = varList[6] #seems deprecated

    def getNumFields(self):
        return self.numField | ((self.alignment << 1) & 0x100)
    def getAlignment(self):
        return self.alignment & 0x7f
class InstanceRepeater:
    def __init__(self,varList):
        self.complexIndex    = varList[0] #index of complex used as the instance
        self.repetitions     = varList[1] #number of instance repetitions
class arrayRepeater:
    def __init__(self,varList):
        self.offset          = varList[0] #offset in array payload section
        self.repetitions     = varList[1] #number of array repetitions
        self.complexIndex    = varList[2] #not necessary for extraction
class Enumeration:
    def __init__(self):
        self.values = dict()
        self.type = 0
class InstanceIndex: #Used for instances with no GUID
    def __init__(self,idx):
        self.idx=idx
    def __eq__(self,other):
        return self.__dict__==other.__dict__
    def __ne__(self,other):
        return self.__dict__!=other.__dict__
    def __hash__(self):
        return hash(self.val)

    def format(self):
        return "Instance%d" % self.idx
    def isNull(self):
        return False

class Complex:
    def __init__(self,desc):
        self.desc=desc
    def get(self,name,critical=True,defaultVal=None):
        for field in self.fields:
            if field.desc.name==name:
                if field.desc.getFieldType()==FieldType.Array:
                    return field.value.fields
                else:
                    return field.value

        #Go up the inheritance chain.
        for field in self.fields:
            if field.desc.getFieldType()==FieldType.Void:
                return field.value.get(name,critical)

        if critical:
            raise Exception("Could not find field with name: "+name)
        else:
            return defaultVal

class Field:
    def __init__(self,desc):
        self.desc=desc
    def link(self,dbx):
        if self.desc.getFieldType()!=FieldType.Class:
            raise Exception("Invalid link, wrong field type\nField name: "+self.desc.name+"\nField type: "+hex(self.desc.getFieldType())+"\nFile name: "+dbx.trueFilename)

        if self.value>>31:
            if dbx.ebxRoot=="":
                raise nullguid("Ebx root path is not specified!")

            extguid=dbx.externalGUIDs[self.value&0x7fffffff]

##            print guidTable[extguid[0]]
            extDbx=Dbx(os.path.join(dbx.ebxRoot,guidTable[extguid[0]]+".ebx").lower(),dbx.ebxRoot)
            for guid, instance in extDbx.instances:
                if guid==extguid[1]:
                    return instance
            raise nullguid("Nullguid link.\nFilename: "+dbx.trueFilename)
        elif self.value!=0:
            for guid, instance in dbx.instances:
                if guid==dbx.internalGUIDs[self.value-1]:
                    return instance
        else:
            raise Exception("Nullguid link.\nFilename: "+dbx.trueFilename)

        raise Exception("Invalid link, could not find target.")

class FieldType:
    Void = 0x0
    DbObject = 0x1
    ValueType = 0x2
    Class = 0x3
    Array = 0x4
    FixedArray = 0x5
    String = 0x6
    CString = 0x7
    Enum = 0x8
    FileRef = 0x9
    Boolean = 0xA
    Int8 = 0xB
    UInt8 = 0xC
    Int16 = 0xD
    UInt16 = 0xE
    Int32 = 0xF
    UInt32 = 0x10
    Int64 = 0x11
    UInt64 = 0x12
    Float32 = 0x13
    Float64 = 0x14
    GUID = 0x15
    SHA1 = 0x16
    ResourceRef = 0x17
    #TODO:
    #??? = 0x18
    #??? = 0x19

    def __init__(self):
        pass

class Stub:
    pass


class Dbx:
    def __init__(self,path,ebxRoot,primOnly=False):
        f=open2(path,"rb")

        #metadata
        magic=f.read(4)
        if magic==b"\xCE\xD1\xB2\x0F":
            self.version=1
            self.bigEndian=False
        elif magic==b"\x0F\xB2\xD1\xCE":
            self.version=1
            self.bigEndian=True
        elif magic==b"\xCE\xD1\xB4\x0F":
            self.version=2
            self.bigEndian=False
        elif magic==b"\x0F\xB4\xD1\xCE": #Probably doesn't exist
            self.version=2
            self.bigEndian=True
        else:
            raise ValueError("The file is not ebx: "+path)

        self.unpack=unpackBE if self.bigEndian else unpackLE
        self.ebxRoot=ebxRoot
        self.trueFilename=""
        self.header=Header(self.unpack("3I6H3I",f.read(36)))
        self.arraySectionstart=self.header.absStringOffset+self.header.lenString+self.header.lenPayload
        self.fileGUID=Guid(f,self.bigEndian)
        while f.tell()%16!=0: f.seek(1,1) #padding
        self.externalGUIDs=[(Guid(f,self.bigEndian),Guid(f,self.bigEndian)) for i in range(self.header.numGUID)]
        self.keywords=str.split(f.read(self.header.lenName).decode(),"\0")
        self.keywordDict=dict((hasher(keyword),keyword) for keyword in self.keywords)
        self.fieldDescriptors=[FieldDescriptor(self.unpack("IHHii",f.read(16)), self.keywordDict,self.version) for i in range(self.header.numField)]
        self.complexDescriptors=[ComplexDescriptor(self.unpack("IIBBHHH",f.read(16)), self.keywordDict) for i in range(self.header.numComplex)]
        self.instanceRepeaters=[InstanceRepeater(self.unpack("2H",f.read(4))) for i in range(self.header.numInstanceRepeater)]
        while f.tell()%16!=0: f.seek(1,1) #padding
        self.arrayRepeaters=[arrayRepeater(self.unpack("3I",f.read(12))) for i in range(self.header.numArrayRepeater)]
        self.enumerations=dict()

        #payload
        f.seek(self.header.absStringOffset+self.header.lenString)
        self.internalGUIDs=[]
        self.instances=[] # (guid, complex)
        nonGUIDindex=0
        self.isPrimaryInstance=True

        for i, instanceRepeater in enumerate(self.instanceRepeaters):
            for repetition in range(instanceRepeater.repetitions):
                #obey alignment of the instance; peek into the complex for that
                while f.tell()%self.complexDescriptors[instanceRepeater.complexIndex].getAlignment()!=0: f.seek(1,1)

                #all instances after numGUIDRepeater have no guid
                if i<self.header.numGUIDRepeater:
                    instanceGUID=Guid(f,self.bigEndian)
                else:
                    #just numerate those instances without guid and assign an int to them.
                    instanceGUID=InstanceIndex(nonGUIDindex)
                    nonGUIDindex+=1
                self.internalGUIDs.append(instanceGUID)

                inst=self.readComplex(instanceRepeater.complexIndex,f,True)
                inst.guid=instanceGUID

                if self.isPrimaryInstance: self.prim=inst
                self.instances.append( (instanceGUID,inst))
                self.isPrimaryInstance=False #the readComplex function has used isPrimaryInstance by now

            if primOnly and not self.isPrimaryInstance: break

        f.close()

        #if no filename found, use the relative input path instead
        #it's just as good though without capitalization
        if self.trueFilename=="":
            self.trueFilename=os.path.relpath(path,ebxRoot).replace("\\","/")[:-4]

    def readComplex(self, complexIndex, f, isInstance=False):
        complexDesc=self.complexDescriptors[complexIndex]
        cmplx=Complex(complexDesc)
        cmplx.offset=f.tell()

        cmplx.fields=[]
        #alignment 4 instances require subtracting 8 for all field offsets and the complex size
        obfuscationShift=8 if (isInstance and cmplx.desc.getAlignment()==4) else 0

        for fieldIndex in range(complexDesc.fieldStartIndex,complexDesc.fieldStartIndex+complexDesc.getNumFields()):
            f.seek(cmplx.offset+self.fieldDescriptors[fieldIndex].offset-obfuscationShift)
            cmplx.fields.append(self.readField(fieldIndex,f))

        f.seek(cmplx.offset+complexDesc.size-obfuscationShift)
        return cmplx

    def readField(self,fieldIndex,f):
        fieldDesc=self.fieldDescriptors[fieldIndex]
        field=Field(fieldDesc)
        typ=fieldDesc.getFieldType()

        if typ==FieldType.Void:
            # Void (inheritance)
            field.value=self.readComplex(fieldDesc.ref,f)

        elif typ==FieldType.ValueType:
            # ValueType
            field.value=self.readComplex(fieldDesc.ref,f)

        elif typ==FieldType.Class:
            # Class (reference)
            field.value=self.unpack("I",f.read(4))[0]

        elif typ==FieldType.Array:
            # Array
            arrayRptr=self.arrayRepeaters[self.unpack("I",f.read(4))[0]]
            arrayCmplxDesc=self.complexDescriptors[fieldDesc.ref]

            f.seek(self.arraySectionstart+arrayRptr.offset)
            arrayCmplx=Complex(arrayCmplxDesc)
            arrayCmplx.fields=[self.readField(arrayCmplxDesc.fieldStartIndex, f) for repetition in
                                    range(arrayRptr.repetitions)]
            field.value=arrayCmplx

        elif typ==FieldType.CString:
            # CString
            startPos=f.tell()
            stringOffset=self.unpack("i",f.read(4))[0]
            if stringOffset==-1:
                field.value="*nullString*"
            else:
                f.seek(self.header.absStringOffset+stringOffset)
                data=b""
                while True:
                    a=f.read(1)
                    if a==b"\x00": break
                    data+=a
                field.value=data.decode("utf-8","backslashreplace")
                f.seek(startPos+4)

                if self.isPrimaryInstance and fieldDesc.name=="Name" and self.trueFilename=="":
                    self.trueFilename=field.value

        elif typ==FieldType.Enum:
            # Enum
            compareValue=self.unpack("i",f.read(4))[0]
            enumComplex=self.complexDescriptors[fieldDesc.ref]

            if fieldDesc.ref not in self.enumerations:
                enumeration=Enumeration()
                enumeration.type=fieldDesc.ref

                for i in range(enumComplex.fieldStartIndex,enumComplex.fieldStartIndex+enumComplex.getNumFields()):
                    enumeration.values[self.fieldDescriptors[i].offset]=self.fieldDescriptors[i].name

                self.enumerations[fieldDesc.ref]=enumeration

            if compareValue not in self.enumerations[fieldDesc.ref].values:
                field.value=str(compareValue)
            else:
                field.value=self.enumerations[fieldDesc.ref].values[compareValue]

        elif typ==FieldType.FileRef:
            # FileRef
            startPos=f.tell()
            stringOffset=self.unpack("i",f.read(4))[0]
            if stringOffset==-1:
                field.value="*nullRef*"
            else:
                f.seek(self.header.absStringOffset + stringOffset)
                data=b""
                while True:
                    a=f.read(1)
                    if a==b"\x00": break
                    data+=a
                field.value=data.decode()
                f.seek(startPos+4)

                if self.isPrimaryInstance and fieldDesc.name=="Name" and self.trueFilename=="":
                    self.trueFilename=field.value

        elif typ==FieldType.Boolean:
            # Boolean
            field.value=self.unpack("?",f.read(1))[0]

        elif typ==FieldType.Int8:
            # Int8
            field.value=self.unpack("b",f.read(1))[0]

        elif typ==FieldType.UInt8:
            # UInt8
            field.value=self.unpack("B",f.read(1))[0]

        elif typ==FieldType.Int16:
            # Int16
            field.value=self.unpack("h",f.read(2))[0]

        elif typ==FieldType.UInt16:
            # UInt16
            field.value=self.unpack("H",f.read(2))[0]

        elif typ==FieldType.Int32:
            # Int32
            field.value=self.unpack("i",f.read(4))[0]

        elif typ==FieldType.UInt32:
            # UInt32
            field.value=self.unpack("I",f.read(4))[0]

        elif typ==FieldType.Int64:
            # Int64
            field.value=self.unpack("q",f.read(8))[0]

        elif typ==FieldType.UInt64:
            # UInt64
            field.value=self.unpack("Q",f.read(8))[0]

        elif typ==FieldType.Float32:
            # Float32
            field.value=self.unpack("f",f.read(4))[0]

        elif typ==FieldType.Float64:
            # Float64
            field.value=self.unpack("d",f.read(8))[0]

        elif typ==FieldType.GUID:
            # Guid
            field.value=Guid(f,self.bigEndian)

        elif typ==FieldType.SHA1:
            # SHA1
            field.value=f.read(20)

        elif typ==FieldType.ResourceRef:
            # ResourceRef
            field.value=self.unpack("Q",f.read(8))[0]

        else:
            # Unknown
            #print("Unknown field type %02x" % type)
            field.value="*unknown field type 0x%02x*" % typ

        return field

    def dump(self,outName):
        print(self.trueFilename)
        f2=open2(outName,"w")
        f2.write(self.fileGUID.format()+"\n")

        for (guid,instance) in self.instances:
            self.writeInstance(f2,instance,guid.format())
            self.recurse(instance.fields,f2,0)

        f2.close()

    def recurse(self, fields, f2, lvl): #over fields
        lvl+=1
        for field in fields:
            typ=field.desc.getFieldType()

            if typ in (FieldType.Void,FieldType.ValueType):
                self.writeField(f2,field,lvl,"::"+field.value.desc.name)
                self.recurse(field.value.fields,f2,lvl)

            elif typ==FieldType.Class:
                towrite=""
                if field.value>>31:
                    extguid=self.externalGUIDs[field.value&0x7fffffff]
                    try: towrite=guidTable[extguid[0]]+"/"+extguid[1].format()
                    except: towrite=extguid[0].format()+"/"+extguid[1].format()
                elif field.value==0:
                    towrite="*nullGuid*"
                else:
                    intGuid=self.internalGUIDs[field.value-1]
                    towrite=intGuid.format()
                self.writeField(f2,field,lvl," "+towrite)

            elif typ==FieldType.Array:
                arrayCmplxDesc=self.complexDescriptors[field.desc.ref]
                arrayFieldDesc=self.fieldDescriptors[arrayCmplxDesc.fieldStartIndex]

                if len(field.value.fields)==0:
                    self.writeField(f2,field,lvl," *nullArray*")
                else:
                    if arrayFieldDesc.getFieldType()==FieldType.Enum and arrayFieldDesc.ref==0: #hack for enum arrays
                        self.writeField(f2,field,lvl,"::"+field.value.desc.name+" #unknown enum")
                    else:
                        self.writeField(f2,field,lvl,"::"+field.value.desc.name)

                    #quick hack so I can add indices to array members while using the same recurse function
                    for index in range(len(field.value.fields)):
                        member=field.value.fields[index]
                        if member.desc.name=="member":
                            desc=copy.deepcopy(member.desc)
                            desc.name="member("+str(index)+")"
                            member.desc=desc
                    self.recurse(field.value.fields,f2,lvl)

            elif typ==FieldType.GUID:
                if field.value.isNull():
                    self.writeField(f2,field,lvl," *nullGuid*")
                else:
                    self.writeField(f2,field,lvl," "+field.value.format())

            elif typ==FieldType.SHA1:
                self.writeField(f2,field,lvl," "+field.value.hex().upper())

            elif typ==FieldType.ResourceRef:
                resRid=field.value
                towrite=" "+str(resRid)
                if resRid in res.resTable:
                    towrite+=" #"+res.resTable[resRid].name
                self.writeField(f2,field,lvl,towrite)

            else:
                self.writeField(f2,field,lvl," "+str(field.value))

    def writeField(self,f,field,lvl,text):
        f.write(lvl*"\t"+field.desc.name+text+"\n")

    def writeInstance(self,f,cmplx,text):
        f.write(cmplx.desc.name+" "+text+"\n")

    def extractAssets(self,chunkFolder,chunkFolder2,resFolder,outputFolder):
        self.chunkFolder=chunkFolder
        self.chunkFolder2=chunkFolder2
        self.outputFolder=outputFolder
        self.resFolder=resFolder

        if self.prim.desc.name=="SoundWaveAsset": self.extractSoundWaveAsset()
        elif self.prim.desc.name=="NewWaveAsset": self.extractNewWaveAsset()
        elif self.prim.desc.name=="LocalizedWaveAsset" : self.extractNewWaveAsset() #inherited from NewWaveAsset
        elif self.prim.desc.name=="HarmonySampleBankAsset": self.extractHarmonyAsset()
        elif self.prim.desc.name=="GinsuAsset": self.extractGenericSoundAsset(".gin")
        elif self.prim.desc.name=="OctaneAsset": self.extractGenericSoundAsset(".gin")
        elif self.prim.desc.name=="MovieTextureAsset": self.extractMovieAsset()
        elif self.prim.desc.name=="MovieTexture2Asset": self.extractMovie2Asset()

    def findChunk(self,chnk):
        if chnk.isNull():
            return None

        ChunkId=chnk.format()
        chnkPath=os.path.join(self.chunkFolder,ChunkId+".chunk")
        if os.path.isfile(chnkPath):
            return chnkPath
        chnkPath=os.path.join(self.chunkFolder2,ChunkId+".chunk")
        if os.path.isfile(chnkPath):
            return chnkPath

        print("Chunk does not exist: "+ChunkId)
        return None

    def extractChunk(self,chnk,ext,idx=-1,totalChunks=0):
        currentChunkName=self.findChunk(chnk)
        if not currentChunkName:
            return

        target=os.path.join(self.outputFolder,self.trueFilename)
        if totalChunks>1: target+=" "+str(idx)
        target+=ext
        makeLongDirs(target)
        shutil.copyfile(currentChunkName,lp(target))

    def extractSPS(self,f,offset,target):
        f.seek(offset)
        if f.read(1)!=b"\x48":
            raise Exception("Wrong SPS header.")

        # Create the target file.
        f2=open2(target,"wb")

        # 0x48=header, 0x44=normal block, 0x45=last block (empty)
        while True:
            f.seek(offset)
            blockStart=unpack(">I",f.read(4))[0]
            blockId=(blockStart&0xFF000000)>>24
            blockSize=blockStart&0x00FFFFFF

            f.seek(offset)
            f2.write(f.read(blockSize))
            offset+=blockSize

            if blockId==0x45:
                break

        f2.close()

    def extractSoundWaveAsset(self):
        print(self.trueFilename)

        histogram=dict() #count the number of times each chunk is used by a variation to obtain the right index

        Chunks=[]
        for i in self.prim.get("Chunks"):
            chnk=Stub()
            Chunks.append(chnk)
            chnk.ChunkId=i.value.get("ChunkId")
            chnk.ChunkSize=i.value.get("ChunkSize")

        Variations=[]
        Segments=[]
        for seg in self.prim.get("Segments"):
            Segment=Stub()
            Segments.append(Segment)
            Segment.SamplesOffset=seg.value.get("SamplesOffset")
            Segment.SeekTableOffset=seg.value.get("SeekTableOffset")
            Segment.SegmentLength=seg.value.get("SegmentLength")

        for var in self.prim.get("RuntimeVariations"):
            Variation=Stub()
            Variations.append(Variation)
            Variation.ChunkIndex=var.value.get("ChunkIndex")
            Variation.FirstSegmentIndex=var.value.get("FirstSegmentIndex")
            Variation.SegmentCount=var.value.get("SegmentCount")

            Variation.Segments=Segments[Variation.FirstSegmentIndex:Variation.FirstSegmentIndex+Variation.SegmentCount]
            Variation.ChunkId=Chunks[Variation.ChunkIndex].ChunkId
            Variation.ChunkSize=Chunks[Variation.ChunkIndex].ChunkSize

            #find the appropriate index
            #the index from the Variations array can get large very fast
            #instead, make my own index starting from 0 for every chunkIndex
            if Variation.ChunkIndex in histogram: #has been used previously already
                Variation.Index=histogram[Variation.ChunkIndex]
                histogram[Variation.ChunkIndex]+=1
            else:
                Variation.Index=0
                histogram[Variation.ChunkIndex]=1

        self.extractSoundVariations(Chunks,Variations)

    def extractNewWaveAsset(self):
        print(self.trueFilename)

        #Cache GUIDs for lookup the first time we encounter NewWaveAsset.
        res.cacheNewWaveResources(self.bigEndian)

        if self.prim.guid in res.newWaves:
            resInfo=res.newWaves[self.prim.guid]
            resPath=os.path.join(self.resFolder,resInfo.getResFilename())
        else:
            if len(res.resTable)!=0:
                print("NewWaveResource not found in table for EBX: " + self.trueFilename)
                return

            #Attempt to fall back to simple name building for compatibility with scripts for newer layouts.
            resPath=os.path.join(self.resFolder,self.trueFilename.lower()+".NewWaveResource")

        if not os.path.isfile(lp(resPath)):
            print("RES does not exist: " + os.path.relpath(resPath,self.resFolder))
            return

        bank=sbr.Bank(lp(resPath))
        histogram=dict() #count the number of times each chunk is used by a variation to obtain the right index

        Chunks=[]
        for i in range(bank.get("Chunks").numElems):
            chnk=Stub()
            Chunks.append(chnk)
            chnk.ChunkId=bank.get("Chunks").get("ChunkId").getGuid(i)
            chnk.ChunkSize=bank.get("Chunks").get("ChunkSize").values[i]

        Variations=[]
        Segments=[]
        for i in range(bank.get("Segments").numElems):
            Segment=Stub()
            Segments.append(Segment)
            Segment.SamplesOffset=bank.get("Segments").get("SamplesOffset").values[i] & (~0x03)
            Segment.SeekTableOffset=bank.get("Segments").get("SeekTableOffset").values[i] & (~0x03)
            Segment.SegmentLength=bank.get("Segments").get("Duration").values[i]

        for i in range(bank.get("Variations").numElems):
            Variation=Stub()
            Variations.append(Variation)
            memchnk=bank.get("Variations").get("MemoryChunkIndex").values[i]
            stmchnk=bank.get("Variations").get("StreamChunkIndex").values[i]
            Variation.ChunkIndex = memchnk>>1 if memchnk&1 else stmchnk>>1
            Variation.FirstSegmentIndex=bank.get("Variations").get("FirstSegmentIndex").values[i]
            Variation.SegmentCount=bank.get("Variations").get("SegmentCount").values[i]

            Variation.Segments=Segments[Variation.FirstSegmentIndex:Variation.FirstSegmentIndex+Variation.SegmentCount]
            Variation.ChunkId=Chunks[Variation.ChunkIndex].ChunkId
            Variation.ChunkSize=Chunks[Variation.ChunkIndex].ChunkSize

            #find the appropriate index
            #the index from the Variations array can get large very fast
            #instead, make my own index starting from 0 for every chunkIndex
            if Variation.ChunkIndex in histogram: #has been used previously already
                Variation.Index=histogram[Variation.ChunkIndex]
                histogram[Variation.ChunkIndex]+=1
            else:
                Variation.Index=0
                histogram[Variation.ChunkIndex]=1

        self.extractSoundVariations(Chunks,Variations)

    def extractSoundVariations(self,Chunks,Variations):
        #everything is laid out neatly now
        #Variation fields: ChunkId, ChunkSize, Index, ChunkIndex, SeekTablesSize, FirstLoopSegmentIndex, LastLoopSegmentIndex, Segments
        #Variation.Segments fields: SamplesOffset, SeekTableOffset, SegmentLength

        ChunkHandles=dict() #for each ebx, keep track of all file handles

        for Variation in Variations:
            try:
                f=ChunkHandles[Variation.ChunkId]
            except:
                currentChunkName=self.findChunk(Variation.ChunkId)
                if not currentChunkName:
                    continue #do NOT return, instead print the messages at the very end

                f=open(currentChunkName,"rb")
                ChunkHandles[Variation.ChunkId]=f

            for ijk in range(len(Variation.Segments)):
                Segment=Variation.Segments[ijk]
                offset=Segment.SamplesOffset

                target=os.path.join(self.outputFolder,self.trueFilename)
                if len(Chunks)>1 or len(Variations)>1 or len(Variation.Segments)>1:
                    target+=" "+str(Variation.ChunkIndex)+" "+str(Variation.Index)+" "+str(ijk)
                target+=".sps"

                self.extractSPS(f,offset,target)

        for key in ChunkHandles:
            ChunkHandles[key].close()

    def extractHarmonyAsset(self):
        print(self.trueFilename)

        Chunks=self.prim.get("Chunks")

        RamChunkIndex=self.prim.get("RamChunkIndex")
        if RamChunkIndex!=0xff:
            chnk=Chunks[RamChunkIndex].value.get("ChunkId")
            self.extractChunk(chnk,".sbr")

        DebugChunkIndex=self.prim.get("DebugChunkIndex")
        if DebugChunkIndex!=0xff:
            chnk=Chunks[DebugChunkIndex].value.get("ChunkId")
            self.extractChunk(chnk,".sbd")

        StreamChunkIndex=self.prim.get("StreamChunkIndex")
        if StreamChunkIndex!=0xff:
            chnk=Chunks[StreamChunkIndex].value.get("ChunkId")
            self.extractChunk(chnk,".sbs")

    def extractGenericSoundAsset(self,ext):
        print(self.trueFilename)

        Chunks=self.prim.get("Chunks")
        for i in range(len(Chunks)):
            field=Chunks[i]
            ChunkId=field.value.get("ChunkId")
            ChunkSize=field.value.get("ChunkSize")
            self.extractChunk(ChunkId,ext,i,len(Chunks))

    def extractMovieAsset(self):
        print(self.trueFilename)

        ext=""
        if self.prim.get("HasVp6",False)!=None:
            #Detect type.
            if self.prim.get("HasVp6"): ext=".vp6"
            elif self.prim.get("HasVp8"): ext=".vp8"
            else: print("Unknown movie type")
        else:
            #Early version, VP6 only.
            ext=".vp6"

        chnk=self.prim.get("ChunkGuid")
        self.extractChunk(chnk,ext)

    def extractMovie2Asset(self):
        print(self.trueFilename)

        chnk=self.prim.get("ChunkGuid")
        self.extractChunk(chnk,".webm")
