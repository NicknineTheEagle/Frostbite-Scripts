import os
from struct import unpack,pack
import ebx

#Choose where you dumped the files and where to put the extracted assets.
dumpDirectory   = r"E:\GameRips\NFS\NFSR\pc\dump"
targetDirectory = r"E:\GameRips\NFS\NFSR\pc\assets"
inputFolder     = r"audio\music"

#These paths are relative to the dumpDirectory. They don't need to be changed.
ebxFolder    = r"bundles\ebx"
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

ebxFolder,chunkFolder,chunkFolder2 = [os.path.join(dumpDirectory, path) for path in (ebxFolder, chunkFolder, chunkFolder2)]
inputFolder=os.path.join(ebxFolder,inputFolder)

print("Generating GUID table...")
ebx.createGuidTableFast(inputFolder,ebxFolder)

for dir0, dirs, ff in os.walk(inputFolder):
    for fname in ff:
        f=open(os.path.join(dir0,fname),"rb")
        dbx=ebx.Dbx(f,fname,ebxFolder)
        f.close()
        dbx.extractChunks(chunkFolder,chunkFolder2,targetDirectory)
