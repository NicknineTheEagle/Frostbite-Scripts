import os
from struct import unpack,pack
import ebx
import getpath

#You can hardcode paths here 
dumpPath        = "" #r"E:\Games\Dragon_Age_Inquisition_Export"
targetPath      = "" #dumpPath+"\ebx" #Choose where you dumped the files and where to put the resulting TXT files.

# helper code from getpath.py to verify existance of directory
dumpDirectory   = getOrCreatePathWithQuery(dumpPath, "enter path to results of dump.py", False) # should exist already
targetDirectory = getOrCreatePathWithQuery(targetPath, "enter path where the files should be extracted", True) # can be created if not
inputFolder     = getRelativePathWithQuery(dumpPath + "bundles\ebx", "", "Enter subfolder (relative to dumpDirectory\bundles\ebx) to restrict result processing.\n If in doubt, leave empty.")  #r"audio\music" #relative to ebxFolder


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
