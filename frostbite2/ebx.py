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
import dds

def unpackLE(typ,data): return unpack("<"+typ,data)
def unpackBE(typ,data): return unpack(">"+typ,data)

guidTable=dict()
parsedEbx=list()

def addEbxGuid(path,ebxRoot):
    if path in parsedEbx:
        return

    #Add EBX GUID and name to the database.
    dbx=Dbx(path,ebxRoot)
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
    def __init__(self,varList): ##all 4byte unsigned integers
        self.absStringOffset     = varList[0]  ## absolute offset for string section start
        self.lenStringToEOF      = varList[1]  ## length from string section start to EOF
        self.numGUID             = varList[2]  ## number of external GUIDs
        self.null                = varList[3]  ## 00000000
        self.numInstanceRepeater = varList[4]
        self.numComplex          = varList[5]  ## number of complex entries
        self.numField            = varList[6]  ## number of field entries
        self.lenName             = varList[7]  ## length of name section including padding
        self.lenString           = varList[8]  ## length of string section including padding
        self.numArrayRepeater    = varList[9]
        self.lenPayload          = varList[10] ## length of normal payload section; the start of the array payload section is absStringOffset+lenString+lenPayload
class FieldDescriptor:
    def __init__(self,varList,keywordDict):
        self.name            = keywordDict[varList[0]]
        self.type            = varList[1]
        self.ref             = varList[2] #the field may contain another complex
        self.offset          = varList[3] #offset in payload section; relative to the complex containing it
        self.secondaryOffset = varList[4]

    def getFieldType(self):
        return (self.type >> 4) & 0x1F
class ComplexDescriptor:
    def __init__(self,varList,keywordDict):
        self.name            = keywordDict[varList[0]]
        self.fieldStartIndex = varList[1] #the index of the first field belonging to the complex
        self.numField        = varList[2] #the total number of fields belonging to the complex
        self.alignment       = varList[3]
        self.type            = varList[4]
        self.size            = varList[5] #total length of the complex in the payload section
        self.secondarySize   = varList[6] #seems deprecated
class InstanceRepeater:
    def __init__(self,varList):
        self.null            = varList[0] #called "internalCount", seems to be always null
        self.repetitions     = varList[1] #number of instance repetitions
        self.complexIndex    = varList[2] #index of complex used as the instance
class arrayRepeater:
    def __init__(self,varList):
        self.offset          = varList[0] #offset in array payload section
        self.repetitions     = varList[1] #number of array repetitions
        self.complexIndex    = varList[2] #not necessary for extraction
class Enumeration:
    def __init__(self):
        self.values = dict()
        self.type = 0

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
                raise Exception("Ebx root path is not specified!")

            extguid=dbx.externalGUIDs[self.value&0x7fffffff]

##            print guidTable[extguid[0]]
            extDbx=Dbx(os.path.join(dbx.ebxRoot,guidTable[extguid[0]]+".ebx").lower(),dbx.ebxRoot)
            for guid, instance in extDbx.instances:
                if guid==extguid[1]:
                    return instance
            raise Exception("Nullguid link.\nFilename: "+dbx.trueFilename)
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

    def __init__(self):
        pass

class Stub:
    pass



class Dbx:
    def __init__(self,path,ebxRoot):
        f=open2(path,"rb")

        #metadata
        magic=f.read(4)
        if magic==b"\xCE\xD1\xB2\x0F":   self.bigEndian=False
        elif magic==b"\x0F\xB2\xD1\xCE": self.bigEndian=True
        else: raise ValueError("The file is not ebx: "+path)

        self.unpack=unpackBE if self.bigEndian else unpackLE
        self.ebxRoot=ebxRoot
        self.trueFilename=""
        self.header=Header(self.unpack("11I",f.read(44)))
        self.arraySectionstart=self.header.absStringOffset+self.header.lenString+self.header.lenPayload
        self.fileGUID, self.primaryInstanceGUID = Guid(f,self.bigEndian), Guid(f,self.bigEndian)
        self.externalGUIDs=[(Guid(f,self.bigEndian),Guid(f,self.bigEndian)) for i in range(self.header.numGUID)]
        self.keywords=str.split(f.read(self.header.lenName).decode(),"\0")
        self.keywordDict=dict((hasher(keyword),keyword) for keyword in self.keywords)
        self.fieldDescriptors=[FieldDescriptor(self.unpack("IHHII",f.read(16)), self.keywordDict) for i in range(self.header.numField)]
        self.complexDescriptors=[ComplexDescriptor(self.unpack("IIBBHHH",f.read(16)), self.keywordDict) for i in range(self.header.numComplex)]
        self.instanceRepeaters=[InstanceRepeater(self.unpack("3I",f.read(12))) for i in range(self.header.numInstanceRepeater)]
        while f.tell()%16!=0: f.seek(1,1) #padding
        self.arrayRepeaters=[arrayRepeater(self.unpack("3I",f.read(12))) for i in range(self.header.numArrayRepeater)]
        self.enumerations=dict()

        #payload
        f.seek(self.header.absStringOffset+self.header.lenString)
        self.internalGUIDs=[]
        self.instances=[] # (guid, complex)
        for instanceRepeater in self.instanceRepeaters:
            for repetition in range(instanceRepeater.repetitions):
                instanceGUID=Guid(f,self.bigEndian)
                self.internalGUIDs.append(instanceGUID)
                if instanceGUID==self.primaryInstanceGUID:
                    self.isPrimaryInstance=True
                else:
                    self.isPrimaryInstance=False
                inst=self.readComplex(instanceRepeater.complexIndex,f)
                inst.guid=instanceGUID

                if self.isPrimaryInstance: self.prim=inst
                self.instances.append((instanceGUID,inst))

        f.close()

        #if no filename found, use the relative input path instead
        #it's just as good though without capitalization
        if self.trueFilename=="":
            self.trueFilename=os.path.relpath(f.name,ebxRoot).replace("\\","/")[:-4]

    def readComplex(self, complexIndex,f):
        complexDesc=self.complexDescriptors[complexIndex]
        cmplx=Complex(complexDesc)

        startPos=f.tell()
        cmplx.fields=[]
        for fieldIndex in range(complexDesc.fieldStartIndex,complexDesc.fieldStartIndex+complexDesc.numField):
            f.seek(startPos+self.fieldDescriptors[fieldIndex].offset)
            cmplx.fields.append(self.readField(fieldIndex,f))

        f.seek(startPos+complexDesc.size)
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

                for i in range(enumComplex.fieldStartIndex,enumComplex.fieldStartIndex+enumComplex.numField):
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

        else:
            # Unknown
            raise Exception("Unknown field type 0x%02x" % typ)

        return field

    def dump(self,outName):
        print(self.trueFilename)
        f2=open2(outName,"w")
        f2.write(self.fileGUID.format()+"\n")

        for (guid,instance) in self.instances:
            if guid==self.primaryInstanceGUID: self.writeInstance(f2,instance,guid.format()+ " #primary instance")
            else: self.writeInstance(f2,instance,guid.format())
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
        elif self.prim.desc.name=="NfsTmxAsset": self.extractGenericSoundAsset(".tmx")
        elif self.prim.desc.name=="MovieTextureAsset": self.extractMovieAsset()
        elif self.prim.desc.name=="TextureAsset": self.extractTextureAsset()
        elif self.prim.desc.name=="NoiseTextureAsset": self.extractTextureAsset()

    def findRes(self,name):
        name=name.lower()
        if name not in res.resTable:
            print("Res not found in RES table: "+name)
            return None

        resInfo=res.resTable[name]
        ext=resInfo.getResExt()
        path=os.path.join(self.resFolder,name+ext)
        if not os.path.isfile(lp(path)):
            print("Res does not exist: "+name)
            return None

        return path

    def extractRes(self,name,ext):
        resName=self.findRes(name)
        if not resName:
            return

        target=os.path.join(self.outputFolder,self.trueFilename)+ext
        makeLongDirs(target)
        shutil.copyfile(lp(resName),lp(target))

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

        variations=[i.link(self) for i in self.prim.get("Variations")]

        Variations=[]

        for var in variations:
            Variation=Stub()
            Variations.append(Variation)
            Variation.ChunkIndex=var.get("ChunkIndex")
##            Variation.SeekTablesSize=var.get("SeekTablesSize")
            Variation.FirstLoopSegmentIndex=var.get("FirstLoopSegmentIndex")
            Variation.LastLoopSegmentIndex=var.get("LastLoopSegmentIndex")


            Variation.Segments=[]
            segs=var.get("Segments")
            for seg in segs:
                Segment=Stub()
                Variation.Segments.append(Segment)
                Segment.SamplesOffset = seg.value.get("SamplesOffset")
                Segment.SeekTableOffset = seg.value.get("SeekTableOffset")
                Segment.SegmentLength = seg.value.get("SegmentLength")

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
                    continue

                f=open(currentChunkName,"rb")
                ChunkHandles[Variation.ChunkId]=f
                #print("Chunk found: "+currentChunkName)

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
        isStreamed=self.prim.get("StreamMovieFile",False,True)

        if isStreamed:
            chnk=self.prim.get("ChunkGuid")
            self.extractChunk(chnk,".vp6")
        else:
            resName=self.prim.get("ResourceName")
            self.extractRes(resName,".vp6")

    def extractTextureAsset(self):
        print(self.trueFilename)
        resName=self.findRes(self.trueFilename)
        if not resName:
            return

        #Read FB texture header.
        class Texture:
            def __init__(self,ebx,f):
                hdr=ebx.unpack("4I4H2s2B16s15I2I16s",f.read(0x80))
                self.version=hdr[0]
                self.type=hdr[1]
                self.format=hdr[2]
                self.flags=hdr[3]
                self.width=hdr[4]
                self.height=hdr[5]
                self.depth=hdr[6]
                self.slices=hdr[7]
                #unused 2 bytes
                self.numMipMaps=hdr[9]
                self.firstMipMap=hdr[10]
                self.chnk=Guid.frombytes(hdr[11],ebx.bigEndian)
                self.mipMapSizes=[int(i) for i in hdr[12:27]]
                self.mipMapChainSize=hdr[27]
                self.nameHash=hdr[28]
                self.texGroup=hdr[29].decode().split("\0",1)[0]

        f=open2(resName,"rb")
        tex=Texture(self,f)
        f.close()

        enum=dds.getFormatEnum(tex.version)
        if not enum:
            print("Unsupported version %d" % tex.version)
            return

        if not dds.remapFormat(enum,tex.format):
            print("Unsupported compression format %d" % tex.format)
            return

        if tex.type not in [0,1,2]:
            print("Unsupported texture type %d" % tex.type)
            return

        #Load image data from the linked chunk.
        chnkPath=self.findChunk(tex.chnk)
        if not chnkPath:
            return

        f=open(chnkPath,"rb")
        texData=f.read()
        f.close()

        #Build DDS header from the data in FB texture header.
        ddsHdr=dds.DDS_HEADER(tex)

        target=os.path.join(self.outputFolder,self.trueFilename+".dds")
        f=open2(target,"wb")
        f.write(ddsHdr.encode())
        f.write(texData)
        f.close()
