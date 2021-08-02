#Res names and res lookup table are handled here.
#Frostbite 3 looks up res files by 64-bit ID.
import os
import pickle
import re
from dbo import Guid

resTypes=dict()
resTable=dict()
unkResTypes=list()

def loadResNames():
    #Load known res type names from the list into types table.
    f=open(r"..\misc\resnames.txt","r")
    data=f.read()
    f.close()
    lines=data.splitlines()

    for line in lines:
        #Skip comments and whitespaces.
        name=re.split("[ \t#]",line,1)[0]
        if not name:
            continue

        #Res types are lowercase names hashed with FNV-1.
        hash=hasher(name.lower())
        resTypes[hash]=name
        #print("%08x : %s" % (hash,name))

def hasher(keyword): #32bit FNV-1 hash with FNV_offset_basis = 5381 and FNV_prime = 33
    hash = 5381
    for byte in keyword:
        hash = (hash*33) ^ ord(byte)
        hash &= 0xffffffff # use & because Python promotes the num instead of intended overflow
    return hash

def getResExt(typ):
    if typ not in resTypes:
        return ".res_%08x" % typ
    return "."+resTypes[typ]

class ResInfo:
    def __init__(self,name,resType,resMeta):
        self.name=name
        self.resType=resType
        self.resMeta=resMeta
    def getResFilename(self):
        return self.name+getResExt(self.resType)

def addToResTable(resRid,name,resType,resMeta):
    if resType not in resTypes and resType not in unkResTypes:
        unkResTypes.append(resType)

    #Null resRid can't be looked up.
    if resRid!=0:
        resTable[resRid]=ResInfo(name,resType,resMeta)

def writeResTable(dumpFolder):
    f=open(os.path.join(dumpFolder,"resTable.bin"),"wb")
    pickle.dump(resTable,f)
    f.close()

    #Log any res types we don't know names for yet.
    if len(unkResTypes)!=0:
        f=open(os.path.join(dumpFolder,"unknownResTypes.txt"),"w")
        for typ in unkResTypes:
            f.write("0x%08x\n" % typ)
        f.close()

def loadResTable(dumpFolder):
    global resTable
    path=os.path.join(dumpFolder,"resTable.bin")
    if not os.path.isfile(path):
        print("WARNING: RES table is missing, it is required to link to RES files!")
        return

    f=open(path,"rb")
    resTable=pickle.load(f)
    f.close()

    #Load res names, too.
    loadResNames()

newWaves=dict()
newWavesCached=False

def cacheNewWaveResources(bigEndian):
    #Special case for NewWaveAssets which look up NewWaveResources by GUID stored in resMeta.
    global newWavesCached
    if newWavesCached:
        return

    if len(resTable)==0:
        print("Falling back to simple NewWaveResource finding method, may not work properly.")
        newWavesCached=True
        return

    print("Caching NewWaveResource GUIDs...")
    typ=hasher("newwaveresource")
    for val in resTable.values():
        if val.resType==typ:
            guid=Guid.frombytes(val.resMeta,bigEndian)
            newWaves[guid]=val

    newWavesCached=True
