import os
import re

resTypes=dict()
unkResTypes=list()

def loadResNames():
    #Load known res names from the list into types table.
    f=open(r"..\misc\resnames.txt","r")
    data=f.read()
    f.close()
    lines=data.splitlines()

    for line in lines:
        #Skip comments and whitespaces
        name=re.split("[ \t#]",line,1)[0]
        if not name:
            continue

        #Res types are lowercase names hashed with FNV-1
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
        if resType not in unkResTypes:
            unkResTypes.append(resType)
        return ".res_%08x" % typ
    return "."+resTypes[typ]

def writeUnkResTypes(dumpFolder):
    #Log any res types we don't know names for yet.
    if len(unkResTypes)!=0:
        f=open(os.path.join(dumpFolder,"unknownResTypes.txt"),"w")
        for typ in unkResTypes:
            f.write("0x%08x\n" % typ)
        f.close()
