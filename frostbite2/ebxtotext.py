import os
from struct import unpack,pack
import ebx

#Choose where you dumped the files and where to put the resulting TXT files.
dumpDirectory   = r"E:\GameRips\NFS\NFSTR\pc\dump"
targetDirectory = r"E:\GameRips\NFS\NFSTR\pc\ebx"
inputFolder     = r"_c4\sound\music" #relative to ebxFolder

#These paths are relative to the dumpDirectory. They don't need to be changed.
ebxFolder    = r"bundles\ebx"
chunkFolder  = r"chunks"
chunkFolder2 = r"bundles\chunks" #if the chunk is not found in the first folder, use this one

##############################################################
##############################################################

ebxFolder,chunkFolder,chunkFolder2 = [os.path.join(dumpDirectory, path) for path in (ebxFolder, chunkFolder, chunkFolder2)]
inputFolder=os.path.join(ebxFolder,inputFolder)

print("Loading GUID table...")
ebx.loadGuidTable(dumpDirectory)

for dir0, dirs, ff in os.walk(inputFolder):
    for fname in ff:
        dbx=ebx.Dbx(os.path.join(dir0,fname),ebxFolder)
        dbx.dump(targetDirectory)
