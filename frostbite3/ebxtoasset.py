import os
from struct import unpack,pack
import ebx

from getpath import getGamePath, getExtractPath


#You can hardcode paths here. If they're not empty, the functions below won't do anything.

# where did you put the results of dumper.py? 
dumpPath        = "" #r"E:\Games\Dragon_Age_Inquisition_Export"

# where do you want to put the extracted assets?
targetPath      = "" #dumpPath+"\_assets" 

# helper code from getpath.py to verify existance of directory
dumpDirectory   = getOrCreatePathWithQuery(dumpPath, "enter path to results of dump.py", False) # should exist already
targetDirectory = getOrCreatePathWithQuery(targetPath, "destination path for created assets (will be created if necessary)", True) 

inputFolder     = getRelativePathWithQuery(dumpPath + "bundles\ebx", "", "Enter subfolder (relative to dumpDirectory\bundles\ebx) to restrict result processing.\n If in doubt, leave empty.")  #r"audio\music" #relative to ebxFolder

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

print("Loading GUID table...")
ebx.loadGuidTable(dumpDirectory)

for dir0, dirs, ff in os.walk(inputFolder):
    for fname in ff:
        dbx=ebx.Dbx(os.path.join(dir0,fname),ebxFolder)
        dbx.extractAssets(chunkFolder,chunkFolder2,targetDirectory)
