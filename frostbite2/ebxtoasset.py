import os
from struct import unpack,pack
import ebx
import res

#Choose where you dumped the files and where to put the extracted assets.
dumpDirectory   = r"E:\GameRips\NFS\NFSTR\pc\dump"
targetDirectory = r"E:\GameRips\NFS\NFSTR\pc\assets"
inputFolder     = r"_c4\sound\music" #relative to ebxFolder

#These paths are relative to the dumpDirectory. They don't need to be changed.
ebxFolder    = r"bundles\ebx"
resFolder    = r"bundles\res"
chunkFolder  = r"chunks"
chunkFolder2 = r"bundles\chunks" #if the chunk is not found in the first folder, use this one

#Run through the sound ebx files, find fields with chunk Guids and fieldName = ChunkId.
#The script will overwrite existing files.

#The filename of the ebx file importing an audio chunk becomes the name of the wav file.
#There are three indices used in the following order.
#1: Variation.ChunkIndex: Some ebx files import several completely independent audio chunk files. This index differentiates between them.
#2: Variation.Index: An ebx may use the same audio chunk for several sound variations, this index keeps them apart.
#3: Segment.Index: A variation may contain several segments, so there is another index.

##############################################################
##############################################################

ebxFolder, resFolder, chunkFolder,chunkFolder2 = [os.path.join(dumpDirectory, path) for path in (ebxFolder, resFolder, chunkFolder, chunkFolder2)]
inputFolder=os.path.join(ebxFolder,inputFolder)

print("Loading GUID table...")
ebx.loadGuidTable(dumpDirectory)
print ("Loading RES table...")
res.loadResTable(dumpDirectory)

for dir0, dirs, ff in os.walk(inputFolder):
    for fname in ff:
        dbx=ebx.Dbx(os.path.join(dir0,fname),ebxFolder)
        dbx.extractAssets(chunkFolder,chunkFolder2,resFolder,targetDirectory)
