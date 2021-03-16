from struct import unpack
from cStringIO import StringIO

def read128(f):
    """Read the next few bytes from file f as LEB128/7bit encoding and return an integer."""
    result,i = 0,0
    while 1:
        byte=ord(f.read(1))
        result|=(byte&127)<<i
        if byte>>7==0: return result
        i+=7
def readNullTerminatedString(f):
    result=""
    while 1:
        char=f.read(1)
        if char=="\x00": return result
        result+=char

        
class Entry:
    """Contains several fields which are simply given in a file one after another.

    An entire toc file (or a cas-enabled bundle) is just a single entry.
    The same format is also used for the chunkMeta of noncas bundle (but there it starts with a field, i.e. the entry is implicit)."""
    
    def __init__(self,f):
        entryType=f.read(1)
        if entryType=="\x82" or entryType=="\x02": #ordinary entry
            if entryType=="\x02":
                readNullTerminatedString(f)
            entrySize=read128(f)
            entryOffset=f.tell()
            while f.tell()-entryOffset<entrySize: #this is kinda redundant, as dataType==0 is a terminator too. However, that's within another function now.
                addField(f,self) #add fields to the entry using reflection
        elif entryType=="\x87": #not sure what that even is
            self.type87Data=f.read(read128(f)-1)
            if f.read(1)!="\x00": raise Exception("Entry does not end with null byte. Position: "+str(f.tell()))
        elif entryType=="\x8f":
            f.read(16)
        else:
            raise Exception("Entry does not start with \\x82 or (rare) \\x87 byte. Position: "+str(f.tell()) + "; entryType: " + entryType)
   
    def get(self, fieldName): return vars(self).get(fieldName) #if the field exists, return the value, else return None
    
def addField(f,entry):
    """Read name and data of a single field from file f and add the field to an entry (or ANY object in fact) using reflection.

    E.g. if a file says 06 cas\0 01, then the function does the same as manually writing: entry.cas=True"""

    offset=f.tell()
    dataType=f.read(1)
    if dataType=="\x00": return
    fieldName=readNullTerminatedString(f)
    #NOTE: vars(entry)["abc"] <=> entry.abc, so I get a really simple syntax at the cost of
    #not really knowing what fields my object will have (unless I use vars again: it's a dict)
    if   dataType=="\x0f": vars(entry)[fieldName]=f.read(16) #id 
    elif dataType=="\x09": vars(entry)[fieldName]=unpack("Q",f.read(8))[0]
    elif dataType=="\x08": vars(entry)[fieldName]=unpack("I",f.read(4))[0]
    elif dataType=="\x06": vars(entry)[fieldName]=True if f.read(1)=="\x01" else False
    elif dataType=="\x02":
        f.seek(offset,0)
        vars(entry)[fieldName]=Entry(f)
    elif dataType=="\x13": vars(entry)[fieldName]=f.read(read128(f)) #the same as above with different content?
    elif dataType=="\x10": vars(entry)[fieldName]=f.read(20) #sha1
    elif dataType=="\x07": #string, length (including trailing null) prefixed as 7bit int
        vars(entry)[fieldName]=f.read(read128(f)-1) #-1 because trailing null
        f.seek(1,1) #trailing null
    elif dataType=="\x01": #list type, containing entries
        entries=[]
        listSize=read128(f)
        listOffset=f.tell() 
        while f.tell()-listOffset<listSize-1: #list ends on nullbyte
            entries.append(Entry(f))
        vars(entry)[fieldName]=entries
        if f.read(1)!="\x00": raise Exception("List does not end with null byte. Position: "+str(f.tell()))
    else: raise Exception("Unknown field data type: "+chr(dataType)+" "+str(f.tell()))

    
def unXor(path):
    """Take a filename (usually toc or cat), decrypt the file if necessary, close it and return the unencrypted data in a memory stream.

    As toc files are ~300 kB at most, make a memory stream even if the file wasn't encrypted in the first place (to get rid of the physical file handle)."""
    
    f=open(path,"rb")
    magic=unpack(">I",f.read(4))[0]
    if magic == 0x00D1CE00: #the file is XOR encrypted and has a signature
        f.seek(296) #skip the signature
        key=[ord(f.read(1))^123 for i in xrange(260)] #bytes 257 258 259 are not used; XOR the key with 123 right away
        encryptedData=f.read()
        f.close()
        data="".join([chr(key[i%257]^ord(encryptedData[i])) for i in xrange(len(encryptedData))]) #go through the data applying one key byte on one data 
    elif magic == 0x00D1CE01: #the file has a signature, but an empty key; it's not encrypted
        f.seek(556) #skip signature + skip empty key
        data=f.read()
    else: #the file is not encrypted; no key + no signature
        f.seek(0)
        data=f.read()
    f.close()
    return StringIO(data)

def readToc(tocPath): #take a filename, decrypt the file and make an entry out of it
    return Entry(unXor(tocPath))
