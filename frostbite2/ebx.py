#requires Python 3
import string
import sys
from struct import unpack,pack
import os
import copy
import pickle
import shutil

##############################################################
##############################################################
def unpackLE(typ,data): return unpack(typ,data)
def unpackBE(typ,data): return unpack(">"+typ,data)

def createGuidTableFast(inputFolder,ebxFolder):
    global guidTable
    guidTable=dict()

    for dir0, dirs, ff in os.walk(inputFolder):
        for fname in ff:
            path=os.path.join(dir0,fname)
            f=open(path,"rb")
            if f.read(4) not in (b"\xCE\xD1\xB2\x0F",b"\x0F\xB2\xD1\xCE"):
                f.close()
                continue
            #grab the file guid directly, absolute offset 48 bytes
            f.seek(48)
            fileguid=f.read(16)
            f.close()
            filename=os.path.relpath(path,ebxFolder)
            filename=os.path.splitext(filename)[0].replace("\\","/")
            guidTable[fileguid]=filename

def createGuidTable(inputFolder):
    global guidTable
    guidTable=dict()

    for dir0, dirs, ff in os.walk(inputFolder):
        for fname in ff:
            f=open(os.path.join(dir0,fname),"rb")
            dbx=Dbx(f,fname)
            guidTable[dbx.fileGUID]=dbx.trueFilename

def makeDirs(path):
    folderPath=os.path.dirname(path)
    if not os.path.isdir(folderPath): os.makedirs(folderPath)

try:
    from ctypes import *
    floatlib = cdll.LoadLibrary("floattostring")
    def formatfloat(num):
        bufType = c_char * 100
        buf = bufType()
        bufpointer = pointer(buf)
        floatlib.convertNum(c_double(num), bufpointer, 100)
        rawstring=(buf.raw)[:buf.raw.find(b"\x00")].decode()
        if rawstring[:2]=="-.": return "-0."+rawstring[2:]
        elif rawstring[0]==".": return "0."+rawstring[1:]
        elif "e" not in rawstring and "." not in rawstring: return rawstring+".0"
        return rawstring
except:
    def formatfloat(num):
        return str(num)
def hasher(keyword): #32bit FNV-1 hash with FNV_offset_basis = 5381 and FNV_prime = 33
    hash = 5381
    for byte in keyword:
        hash = (hash*33) ^ ord(byte)
    return hash & 0xffffffff # use & because Python promotes the num instead of intended overflow
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
class Complex:
    def __init__(self,desc,dbxhandle):
        self.desc=desc
        self.dbx=dbxhandle #lazy
    def get(self,name):
        pathElems=name.split("/")
        curPos=self
        if pathElems[-1].find("::")!=-1: #grab a complex
            for elem in pathElems:
                try:
                    curPos=curPos.go1(elem)
                except Exception as e:
                    raise Exception("Could not find complex with name: "+str(e)+"\nFull path: "+name+"\nFilename: "+self.dbx.trueFilename)
            return curPos
        #grab a field instead
        for elem in pathElems[:-1]:
            try:
                curPos=curPos.go1(elem)
            except Exception as e:
                raise Exception("Could not find complex with name: "+str(e)+"\nFull path: "+name+"\nFilename: "+self.dbx.trueFilename)
        for field in curPos.fields:
            if field.desc.name==pathElems[-1]:
                return field

        raise Exception("Could not find field with name: "+name+"\nFilename: "+self.dbx.trueFilename)

    def go1(self,name): #go once
        for field in self.fields:
            if field.desc.type in (0x0029, 0xd029,0x0000,0x0041):
                if field.desc.name+"::"+field.value.desc.name == name:
                    return field.value
        raise Exception(name)


class Field:
    def __init__(self,desc,dbx):
        self.desc=desc
        self.dbx=dbx
    def link(self):
        if self.desc.type!=0x0035: raise Exception("Invalid link, wrong field type\nField name: "+self.desc.name+"\nField type: "+hex(self.desc.type)+"\nFile name: "+self.dbx.trueFilename)

        if self.value>>31:
            if self.dbx.ebxRoot=="":
                raise nullguid("Ebx root path is not specified!")
            
            extguid=self.dbx.externalGUIDs[self.value&0x7fffffff]

            for existingDbx in dbxArray:
                if existingDbx.fileGUID==extguid[0]:
                    for guid, instance in existingDbx.instances:
                        if guid==extguid[1]:
                            return instance

            f=openEbx(os.path.join(self.dbx.ebxRoot,guidTable[extguid[0]]+".ebx"))
##            print guidTable[extguid[0]]
            dbx=Dbx(f)
            dbxArray.append(dbx)
            for guid, instance in dbx.instances:
                if guid==extguid[1]:
                    return instance
            raise nullguid("Nullguid link.\nFilename: "+self.dbx.trueFilename)
        elif self.value!=0:
            for guid, instance in self.dbx.instances:
                if guid==self.dbx.internalGUIDs[self.value-1]:
                    return instance
        else:
            raise nullguid("Nullguid link.\nFilename: "+self.dbx.trueFilename)

        raise Exception("Invalid link, could not find target.")

    def getlinkguid(self):
        if self.desc.type!=0x0035: raise Exception("Invalid link, wrong field type\nField name: "+self.desc.name+"\nField type: "+hex(self.desc.type)+"\nFile name: "+self.dbx.trueFilename)

        if self.value>>31:
            return "".join(self.dbx.externalGUIDs[self.value&0x7fffffff])
        elif self.value!=0:
            return self.dbx.fileGUID+self.dbx.internalGUIDs[self.value-1]
        else:
            raise nullguid("Nullguid link.\nFilename: "+self.dbx.trueFilename)
    def getlinkname(self):
        if self.desc.type!=0x0035: raise Exception("Invalid link, wrong field type\nField name: "+self.desc.name+"\nField type: "+hex(self.desc.type)+"\nFile name: "+self.dbx.trueFilename)

        if self.value>>31:
            return guidTable[self.dbx.externalGUIDs[self.value&0x7fffffff][0]]+"/"+self.dbx.externalGUIDs[self.value&0x7fffffff][1]
        elif self.value!=0:
            return self.dbx.trueFilename+"/"+self.dbx.internalGUIDs[self.value-1]
        else:
            raise nullguid("Nullguid link.\nFilename: "+self.dbx.trueFilename)
        

def openEbx(fname):
    f=open(fname,"rb")
    if f.read(4) not in (b"\xCE\xD1\xB2\x0F",b"\x0F\xB2\xD1\xCE"):
        f.close()
        raise Exception("Invalid EBX file: "+fname)
    return f

class nullguid(Exception):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)


numDict={0xc0cd:("B",1) ,0x0035:("I",4),0xc10d:("I",4),0xc14d:("d",8),0xc0ad:("?",1),0xc0fd:("i",4),0xc0bd:("b",1),0xc0ed:("h",2), 0xc0dd:("H",2), 0xc13d:("f",4)}


class Stub:
    pass

class Dbx:
    def __init__(self,f,relPath,ebxRoot=""):
        magic=f.read(4)
        if magic==b"\xCE\xD1\xB2\x0F":   self.unpack=unpackLE
        elif magic==b"\x0F\xB2\xD1\xCE": self.unpack=unpackBE
        else: raise ValueError("The file is not ebx: "+relPath)
        self.ebxRoot=ebxRoot
        self.trueFilename=""
        self.header=Header(self.unpack("11I",f.read(44)))
        self.arraySectionstart=self.header.absStringOffset+self.header.lenString+self.header.lenPayload
        self.fileGUID, self.primaryInstanceGUID = f.read(16), f.read(16)
        self.externalGUIDs=[(f.read(16),f.read(16)) for i in range(self.header.numGUID)]
        self.keywords=str.split(f.read(self.header.lenName).decode(),"\0")
        self.keywordDict=dict((hasher(keyword),keyword) for keyword in self.keywords)
        self.fieldDescriptors=[FieldDescriptor(self.unpack("IHHII",f.read(16)), self.keywordDict) for i in range(self.header.numField)]
        self.complexDescriptors=[ComplexDescriptor(self.unpack("IIBBHHH",f.read(16)), self.keywordDict) for i in range(self.header.numComplex)]
        self.instanceRepeaters=[InstanceRepeater(self.unpack("3I",f.read(12))) for i in range(self.header.numInstanceRepeater)]
        while f.tell()%16!=0: f.seek(1,1) #padding
        self.arrayRepeaters=[arrayRepeater(self.unpack("3I",f.read(12))) for i in range(self.header.numArrayRepeater)]

        #payload
        f.seek(self.header.absStringOffset+self.header.lenString)
        self.internalGUIDs=[]
        self.instances=[] # (guid, complex)
        for instanceRepeater in self.instanceRepeaters:
            for repetition in range(instanceRepeater.repetitions):
                instanceGUID=f.read(16)
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


    def readComplex(self, complexIndex,f):
        complexDesc=self.complexDescriptors[complexIndex]
        cmplx=Complex(complexDesc,self)

        startPos=f.tell()
        cmplx.fields=[]
        for fieldIndex in range(complexDesc.fieldStartIndex,complexDesc.fieldStartIndex+complexDesc.numField):
            f.seek(startPos+self.fieldDescriptors[fieldIndex].offset)
            cmplx.fields.append(self.readField(fieldIndex,f))

        f.seek(startPos+complexDesc.size)
        return cmplx


    def readField(self,fieldIndex,f):
        fieldDesc = self.fieldDescriptors[fieldIndex]
        field=Field(fieldDesc,self)

        if fieldDesc.type in (0x0029, 0xd029,0x0000,0x8029):
            field.value=self.readComplex(fieldDesc.ref,f)
        elif fieldDesc.type==0x0041:
            arrayRepeater=self.arrayRepeaters[self.unpack("I",f.read(4))[0]]
            arrayComplexDesc=self.complexDescriptors[fieldDesc.ref]

##            if arrayRepeater.repetitions==0: field.value = "*nullArray*"
            f.seek(self.arraySectionstart+arrayRepeater.offset)
            arrayComplex=Complex(arrayComplexDesc,self)
            arrayComplex.fields=[self.readField(arrayComplexDesc.fieldStartIndex,f) for repetition in range(arrayRepeater.repetitions)]
            field.value=arrayComplex

        elif fieldDesc.type in (0x407d, 0x409d):
            startPos=f.tell()
            f.seek(self.header.absStringOffset+self.unpack("I",f.read(4))[0])
            data=b""
            while 1:
                a=f.read(1)
                if a==b"\x00": break
                else: data+=a
            f.seek(startPos+4)

            if len(data)==0: field.value="*nullString*" #actually the string is ""
            else: field.value=data.decode()

            if self.isPrimaryInstance and self.trueFilename=="" and fieldDesc.name=="Name": self.trueFilename=field.value


        elif fieldDesc.type in (0x0089,0xc089): #incomplete implementation, only gives back the selected string
            compareValue=self.unpack("I",f.read(4))[0]
            enumComplex=self.complexDescriptors[fieldDesc.ref]

            if enumComplex.numField==0:
                field.value="*nullEnum*"
            for fieldIndex in range(enumComplex.fieldStartIndex,enumComplex.fieldStartIndex+enumComplex.numField):
                if self.fieldDescriptors[fieldIndex].offset==compareValue:
                    field.value=self.fieldDescriptors[fieldIndex].name
                    break
        elif fieldDesc.type==0xc15d:
            field.value=f.read(16)
        #elif fieldDesc.type == 0xc13d:
        #    field.value=formatfloat(self.unpack("f",f.read(4))[0])
        elif fieldDesc.type==0x417d:
            field.value=f.read(24)
        else:
            try:
                (typ,length)=numDict[fieldDesc.type]
                num=self.unpack(typ,f.read(length))[0]
                field.value=num
            except:
                #print("Unknown field type: "+hex(fieldDesc.type)+" File name: "+self.trueFilename)
                field.value="*unknown field type*"+" #"+hex(fieldDesc.type)

        return field


    def dump(self,outputFolder):
        if not self.trueFilename: self.trueFilename=self.fileGUID.hex()
        
        outName=os.path.join(outputFolder,self.trueFilename+".txt")
        makeDirs(outName)
        f2=open(outName,"w")
        print(self.trueFilename)

        for (guid,instance) in self.instances:
            if instance.desc.name:
                if guid==self.primaryInstanceGUID: self.writeInstance(f2,instance,guid.hex()+ " #primary instance")
                else: self.writeInstance(f2,instance,guid.hex())
                self.recurse(instance.fields,f2,0)
        f2.close()

    def recurse(self, fields,f2, lvl): #over fields
        lvl+=1
        for field in fields:
            if field.desc.type in (0xc14d, 0xc0fd, 0xc10d, 0xc0ed, 0xc0dd, 0xc0bd, 0xc0ad, 0x407d, 0x409d, 0x0089, 0xc0cd, 0xc089):
                self.writeField(f2,field,lvl," "+str(field.value))
            elif field.desc.type == 0xc13d:
                self.writeField(f2,field,lvl," "+formatfloat(field.value))
            elif field.desc.type == 0xc15d:
                self.writeField(f2,field,lvl," "+field.value.hex().upper()) #upper case=> chunk guid
            elif field.desc.type == 0x0035:
                towrite=""
                if field.value>>31:
                    extguid=self.externalGUIDs[field.value&0x7fffffff]
                    try: towrite=guidTable[extguid[0]]+"/"+extguid[1].hex()
                    except: towrite=extguid[0].hex()+"/"+extguid[1].hex()
                elif field.value==0: towrite="*nullGuid*"
                else: towrite=self.internalGUIDs[field.value-1].hex()
                self.writeField(f2,field,lvl," "+towrite)
            elif field.desc.type==0x0041:
                if len(field.value.fields)==0:
                    self.writeField(f2,field,lvl," *nullArray*")
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
            else:
                try:
                    self.writeField(f2,field,lvl,"::"+field.value.desc.name)
                    self.recurse(field.value.fields,f2,lvl)
                except:
                    self.writeField(f2,field,lvl," "+str(field.value))

    def writeField(self,f,field,lvl,text):
        f.write(lvl*"\t"+field.desc.name+text+"\n")
        
    def writeInstance(self,f,cmplx,text):  
        f.write(cmplx.desc.name+" "+text+"\n")

    def extractChunks(self,chunkFolder,chunkFolder2,resFolder,outputFolder):
        self.chunkFolder=chunkFolder
        self.chunkFolder2=chunkFolder2
        self.outputFolder=outputFolder
        self.resFolder=resFolder

        if self.prim.desc.name=="SoundWaveAsset": self.extractSPS()
        elif self.prim.desc.name=="MovieTextureAsset": self.extractVP6()

    def findRes(self):
        return os.path.join(self.resFolder,os.path.normpath(self.trueFilename.lower())+".res")

    def findChunk(self,chnk):
        # Try ID as is.
        ChunkId=chnk.hex()

        chnkPath=os.path.join(self.chunkFolder,ChunkId+".chunk")
        if os.path.isfile(chnkPath):
            return chnkPath
        chnkPath=os.path.join(self.chunkFolder2,ChunkId+".chunk")
        if os.path.isfile(chnkPath):
            return chnkPath
        
        # Check if ID is obfuscated (usually the case in console versions).
        obfuscationPermutation=[3,2,1,0,5,4,7,6,8,9,10,11,12,13,14,15]
        chnk=bytes([chnk[permute] for permute in obfuscationPermutation])
        ChunkId=chnk.hex()
        
        chnkPath=os.path.join(self.chunkFolder,ChunkId+".chunk")
        if os.path.isfile(chnkPath):
            return chnkPath
        chnkPath=os.path.join(self.chunkFolder2,ChunkId+".chunk")
        if os.path.isfile(chnkPath):
            return chnkPath
        
        return ""

    def extractSPS(self):
        histogram=dict() #count the number of times each chunk is used by a variation to obtain the right index

        Chunks=[]
        for i in self.prim.get("$::SoundDataAsset/Chunks::array").fields:
            chnk=Stub()
            Chunks.append(chnk)
            chnk.ChunkId=i.value.get("ChunkId").value
            chnk.ChunkSize=i.value.get("ChunkSize").value

        variations=[i.link() for i in self.prim.get("Variations::array").fields]

        Variations=[]

        for var in variations:
            Variation=Stub()
            Variations.append(Variation)
            Variation.ChunkIndex=var.get("ChunkIndex").value
##            Variation.SeekTablesSize=var.get("SeekTablesSize").value
            Variation.FirstLoopSegmentIndex=var.get("FirstLoopSegmentIndex").value
            Variation.LastLoopSegmentIndex=var.get("LastLoopSegmentIndex").value


            Variation.Segments=[]
            segs=var.get("Segments::array").fields
            for seg in segs:
                Segment=Stub()
                Variation.Segments.append(Segment)
                Segment.SamplesOffset = seg.value.get("SamplesOffset").value
                Segment.SeekTableOffset = seg.value.get("SeekTableOffset").value
                Segment.SegmentLength = seg.value.get("SegmentLength").value

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

        chunkErrors=set() #
        for Variation in Variations:
            try:
                f=ChunkHandles[Variation.ChunkId]
            except:
                currentChunkName=self.findChunk(Variation.ChunkId)
                if currentChunkName=="":
                    chunkErrors.add("Chunk does not exist: "+Variation.ChunkId.hex().upper())
                    continue #do NOT return, instead print the messages at the very end

                f=open(currentChunkName,"rb")
                ChunkHandles[Variation.ChunkId]=f
                #print("Chunk found: "+currentChunkName)
        
            for ijk in range(len(Variation.Segments)):
                Segment=Variation.Segments[ijk]
                offset=Segment.SamplesOffset

                f.seek(offset)
                headerId=unpack(">B",f.read(1))[0]
                if headerId!=0x48:
                    raise Exception("Wrong SPS header.")

                # Create the target file.
                target=os.path.join(self.outputFolder,self.trueFilename)
                if len(Chunks)>1 or len(Variations)>1 or len(Variation.Segments)>1:
                    target+=" "+str(Variation.ChunkIndex)+" "+str(Variation.Index)+" "+str(ijk)
                target+=".sps"
                    
                makeDirs(target)
                f2=open(target,"wb")

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

        for key in ChunkHandles:
            ChunkHandles[key].close()
        print(self.trueFilename)

        for message in chunkErrors:
            print(message)

    def extractVP6(self):
        chnk=self.prim.get("ChunkGuid").value
        if chnk.hex()=="00000000000000000000000000000000":
            filename=self.findRes()
            if not os.path.isfile(filename):
                print("Res does not exist: "+self.trueFilename)
                return
        else:
            filename=self.findChunk(chnk)      
            if filename=="":
                print("Chunk does not exist: "+chnk.hex().upper())
                return

        target=os.path.join(self.outputFolder,self.trueFilename)+".vp6"
        makeDirs(target)
        shutil.copyfile(filename,target)
        print(self.trueFilename)
