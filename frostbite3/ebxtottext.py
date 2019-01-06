import os
from struct import unpack,pack
import ebx

#Choose where you dumped the files and where to put the resulting TXT files:
dumpDirectory   = r"E:\GameRips\NFS\NFSR\pc\dump"
targetDirectory = r"E:\GameRips\NFS\NFSR\pc\ebx"
inputFolder     = r"audio\music"

#These paths are relative to the dumpDirectory. They don't need to be changed.
ebxFolder    = r"bundles\ebx"
chunkFolder  = r"chunks"
chunkFolder2 = r"bundles\chunks" #if the chunk is not found in the first folder, use this one

#the script can use the actual filenames in the explorer for the guid table (faster)
#or it can parse almost the entire file to retrieve the filename (slow, but necessary when the explorer names are just hashes)
#It's still rather slow either way. Also note that the explorer names are all lower case.
#Thus use False for proper capitalization and True if you want faster progress.
useExplorerNames=False #True/False

#Note: This is not about the filenames themselves, which are always capitalized. It's about fields in one file making
#references to another file; compare these two lines in LevelListReport.txt:
#True:  levels/coop_002/coop_002/description_win32/4c89939b7a8f046a1658504d64b5b4da
#False: Levels/COOP_002/COOP_002/Description_Win32/4c89939b7a8f046a1658504d64b5b4da

#though it should work fine without change too.

##############################################################
##############################################################

ebxFolder,chunkFolder,chunkFolder2 = [os.path.join(dumpDirectory, path) for path in (ebxFolder, chunkFolder, chunkFolder2)]
inputFolder=os.path.join(ebxFolder,inputFolder)

print("Generating GUID table...")
if useExplorerNames:
    ebx.createGuidTableFast(inputFolder,ebxFolder)
else:
    ebx.createGuidTable(inputFolder)

for dir0, dirs, ff in os.walk(inputFolder):
    for fname in ff:
        f=open(os.path.join(dir0,fname),"rb")
        dbx=ebx.Dbx(f,fname,ebxFolder)
        f.close()
        dbx.dump(outputFolder)
