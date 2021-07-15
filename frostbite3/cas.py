#Take a dict and fill it using a cat file: sha1 vs (offset, size, cas path)
#Cat files are always little endian.
import dbo
import os
from struct import pack,unpack

catDict=dict()

class CatEntry:
    def __init__(self,f,casDirectory,version):
        if version<3:
            self.offset,self.size,casNum=unpack("<III",f.read(12))
        else:
            self.offset,self.size,unk,casNum=unpack("<IIII",f.read(16))

        self.path=os.path.join(casDirectory,"cas_%02d.cas" % casNum)

def readCat1(catPath):
    #2013, original version.
    cat=dbo.unXor(catPath)
    cat.seek(0,2) #get eof
    catSize=cat.tell()
    cat.seek(16) #skip nyan
    casDirectory=os.path.dirname(catPath)

    while cat.tell()!=catSize:
        sha1=cat.read(20)
        catDict[sha1]=CatEntry(cat,casDirectory,1)

def readCat2(catPath):
    #2015 (SWBF Beta), added the number of entries in the header and a new section with unknown data (usually empty).
    cat=dbo.unXor(catPath)
    cat.seek(16) #skip nyan
    numEntries, unk = unpack("<II",cat.read(8))
    casDirectory=os.path.dirname(catPath)

    for i in range(numEntries):
        sha1=cat.read(20)
        catDict[sha1]=CatEntry(cat,casDirectory,2)

def readCat3(catPath):
    #2015 (SWBF Final), added a a new var (always 0?) to cat entry.
    cat=dbo.unXor(catPath)
    cat.seek(16) #skip nyan
    numEntries, unk = unpack("<II",cat.read(8))
    casDirectory=os.path.dirname(catPath)

    for i in range(numEntries):
        sha1=cat.read(20)
        catDict[sha1]=CatEntry(cat,casDirectory,3)

def readCat4(catPath):
    #2017, added more unknown sections.
    cat=dbo.unXor(catPath)
    cat.seek(16) #skip nyan
    numEntries, unk, unk2, unk3 = unpack("<IIQQ",cat.read(24))
    casDirectory=os.path.dirname(catPath)

    for i in range(numEntries):
        sha1=cat.read(20)
        catDict[sha1]=CatEntry(cat,casDirectory,4)
