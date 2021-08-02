#This script runs through all toc files it can find and uses that information to extract the files to a target directory.
#Often the assets are actually stored in cascat archives (the sbtoc knows where to search in the cascat), which is taken care of too.
#The script does not overwrite existing files (mainly because 10 sbtocs pointing at the same asset in the cascat would make the extraction time unbearable).
import dbo
import noncas
import ebx
import payload
import cas
import das
import os
from struct import pack,unpack
import res

#Adjust paths here.
#do yourself a favor and don't dump into the Users folder (or it might complain about permission)

gameDirectory   = r"D:\Games\OriginGames\Need for Speed(TM) Rivals"
targetDirectory = r"E:\GameRips\NFS\NFSR\pc\dump"

#####################################
#####################################

def dump(tocPath,baseTocPath,outPath):
    """Take the filename of a toc and dump all files to the targetFolder."""

    #Depending on how you look at it, there can be up to 2*(3*3+1)=20 different cases:
    #    The toc has a cas flag which means all assets are stored in the cas archives. => 2 options
    #        Each bundle has either a delta or base flag, or no flag at all. => 3 options
    #            Each file in the bundle is one of three types: ebx/res/chunks => 3 options
    #        The toc itself contains chunks. => 1 option
    #
    #Simplify things by ignoring base bundles (they just state that the unpatched bundle is used),
    #which is alright, as the user needs to dump the unpatched files anyway.
    #
    #Additionally, add some common fields to the ebx/res/chunks entries so they can be treated the same.
    #=> 6 cases.

    toc=dbo.readToc(tocPath)
    if not (toc.get("bundles") or toc.get("chunks")): return #there's nothing to extract (the sb might not even exist)

    sbPath=tocPath[:-3]+"sb"
    sb=open(sbPath,"rb")

    chunkPathToc=os.path.join(outPath,"chunks")
    bundlePath=os.path.join(outPath,"bundles")
    ebxPath=os.path.join(bundlePath,"ebx")
    resPath=os.path.join(bundlePath,"res")
    chunkPath=os.path.join(bundlePath,"chunks")

    ###read the bundle depending on the four types (+cas+delta, +cas-delta, -cas+delta, -cas-delta) and choose the right function to write the payload
    if toc.get("cas"):
        for tocEntry in toc.get("bundles"): #id offset size, size is redundant
            if tocEntry.get("base"): continue #Patched bundle. However, use the unpatched bundle because no file was patched at all.

            sb.seek(tocEntry.get("offset"))
            bundle=dbo.DbObject(sb)
                    
            #pick the right function
            if tocEntry.get("delta"):
                writePayload=payload.casPatchedBundlePayload
            else:
                writePayload=payload.casBundlePayload

            for entry in bundle.get("ebx",list()): #name sha1 size originalSize
                path=os.path.join(ebxPath,entry.get("name")+".ebx")
                if writePayload(entry,path,False):
                    ebx.addEbxGuid(path,ebxPath)

            for entry in bundle.get("res",list()): #name sha1 size originalSize resRid resType resMeta
                res.addToResTable(entry.get("resRid"),entry.get("name"),entry.get("resType"),entry.get("resMeta"))
                path=os.path.join(resPath,entry.get("name")+res.getResExt(entry.get("resType")))
                writePayload(entry,path,False)

            for entry in bundle.get("chunks",list()): #id sha1 size logicalOffset logicalSize chunkMeta::h32 chunkMeta::meta
                path=os.path.join(chunkPath,entry.get("id").format()+".chunk")
                writePayload(entry,path,True)

        #Deal with the chunks which are defined directly in the toc.
        #These chunks do NOT know their originalSize.
        for entry in toc.get("chunks"): #id sha1
            targetPath=os.path.join(chunkPathToc,entry.get("id").format()+".chunk")
            payload.casChunkPayload(entry,targetPath)
    else:
        for tocEntry in toc.get("bundles"): #id offset size, size is redundant
            if tocEntry.get("base"): continue #Patched bundle. However, use the unpatched bundle because no file was patched at all.

            sb.seek(tocEntry.get("offset"))

            if tocEntry.get("delta"):
                #The sb currently points at the delta file.
                #Read the unpatched toc of the same name to get the base bundle.
                baseToc=dbo.readToc(baseTocPath)
                for baseTocEntry in baseToc.get("bundles"):
                    if baseTocEntry.get("id").lower() == tocEntry.get("id").lower():
                        break
                else: #if no base bundle has with this name has been found:
                    pass #use the last base bundle. This is okay because it is actually not used at all (the delta has uses instructionType 3 only).
                    
                basePath=baseTocPath[:-3]+"sb"
                base=open(basePath,"rb")
                base.seek(baseTocEntry.get("offset"))
                bundle=noncas.patchedBundle(base, sb) #create a patched bundle using base and delta
                base.close()
                writePayload=payload.noncasPatchedBundlePayload
                sourcePath=[basePath,sbPath] #base, delta
            else:
                bundle=noncas.unpatchedBundle(sb)
                writePayload=payload.noncasBundlePayload
                sourcePath=sbPath

            for entry in bundle.ebx:
                path=os.path.join(ebxPath,entry.name+".ebx")
                if writePayload(entry,path,sourcePath):
                    ebx.addEbxGuid(path,ebxPath)

            for entry in bundle.res:
                res.addToResTable(entry.resRid,entry.name,entry.resType,entry.resMeta)
                path=os.path.join(resPath,entry.name+res.getResExt(entry.resType))
                writePayload(entry,path,sourcePath)

            for entry in bundle.chunks:
                path=os.path.join(chunkPath,entry.id.format()+".chunk")
                writePayload(entry,path,sourcePath)

        #Deal with the chunks which are defined directly in the toc.
        #These chunks do NOT know their originalSize.
        for entry in toc.get("chunks"): #id offset size
            targetPath=os.path.join(chunkPathToc,entry.get("id").format()+".chunk")
            payload.noncasChunkPayload(entry,targetPath,sbPath)

    sb.close()



def dumpRoot(dataDir,patchDir,outPath):
    os.makedirs(outPath,exist_ok=True)

    for dir0, dirs, ff in os.walk(dataDir):
        for fname in ff:
            if fname[-4:]==".toc":
                fname=os.path.join(dir0,fname)
                localPath=os.path.relpath(fname,dataDir)
                print(localPath)

                #Check if there's a patched version and extract it first.
                patchedName=os.path.join(patchDir,localPath)
                if os.path.isfile(patchedName):
                    dump(patchedName,fname,outPath)

                dump(fname,None,outPath)

def findCats(dataDir,patchDir,readCat):
    #Read all cats in the specified directory.
    for dir0, dirs, ff in os.walk(dataDir):
        for fname in ff:
            if fname=="cas.cat":
                fname=os.path.join(dir0,fname)
                localPath=os.path.relpath(fname,dataDir)
                print("Reading %s..." % localPath)
                readCat(fname)

                #Check if there's a patched version.
                patchedName=os.path.join(patchDir,localPath)
                if os.path.isfile(patchedName):
                    print("Reading patched %s..." % os.path.relpath(patchedName,patchDir))
                    readCat(patchedName)

#make the paths absolute and normalize the slashes
gameDirectory=os.path.normpath(gameDirectory)
targetDirectory=os.path.normpath(targetDirectory) #it's an absolute path already
payload.zstdInit()

print("Loading RES names...")
res.loadResNames()

#Load layout.toc
tocLayout=dbo.readToc(os.path.join(gameDirectory,"Data","layout.toc"))

if not tocLayout.getSubObject("installManifest") or \
    not tocLayout.getSubObject("installManifest").getSubObject("installChunks"):
    if not os.path.isfile(os.path.join(gameDirectory,"Data","das.dal")):
        #Old layout similar to Frostbite 2 with a single cas.cat.
        #Can also be non-cas.
        dataDir=os.path.join(gameDirectory,"Data")
        updateDir=os.path.join(gameDirectory,"Update")
        patchDir=os.path.join(updateDir,"Patch","Data")

        if not tocLayout.getSubObject("installManifest"):
            readCat=cas.readCat1
        else:
            readCat=cas.readCat2 #Star Wars: Battlefront Beta

        catPath=os.path.join(dataDir,"cas.cat") #Seems to always be in the same place.
        if os.path.isfile(catPath):
            print("Reading cat entries...")
            readCat(catPath)

            #Check if there's a patched version.
            patchedCat=os.path.join(patchDir,os.path.relpath(catPath,dataDir))
            if os.path.isfile(patchedCat):
                print("Reading patched cat entries...")
                readCat(patchedCat)

        if os.path.isdir(updateDir):
            #First, extract all DLCs.
            for dir in os.listdir(updateDir):
                if dir=="Patch":
                    continue

                print("Extracting DLC %s..." % dir)
                dumpRoot(os.path.join(updateDir,dir,"Data"),patchDir,targetDirectory)

        #Now extract the base game.
        print("Extracting main game...")
        dumpRoot(dataDir,patchDir,targetDirectory)
    else:
        #Special case for Need for Speed: Edge. Same as early FB3 but uses das.dal instead of cas.cat.
        dataDir=os.path.join(gameDirectory,"Data")

        print("Reading dal entries...")
        dalPath=os.path.join(dataDir,"das.dal")
        das.readDal(dalPath)

        print("Extracting main game...")
        das.dumpRoot(dataDir,targetDirectory)
        print("Extracting FE...")
        das.dumpFE(dataDir,targetDirectory)
else:
    #New version with multiple cats split into install groups, seen in 2015 and later games.
    #Appears to always use cas.cat and never use delta bundles, patch just replaces bundles fully.
    dataDir=os.path.join(gameDirectory,"Data")
    updateDir=os.path.join(gameDirectory,"Update")
    patchDir=os.path.join(gameDirectory,"Patch")

    #Detect cat version.
    if tocLayout.getSubObject("installManifest").get("maxTotalSize")!=None:
        readCat=cas.readCat3
    else:
        readCat=cas.readCat4

    if os.path.isdir(updateDir):
        #First, extract all DLCs.
        for dir in os.listdir(updateDir):
            print("Extracting DLC %s..." % dir)
            dir=os.path.join(updateDir,dir,"Data")
            findCats(dir,patchDir,readCat)
            dumpRoot(dir,patchDir,targetDirectory)

    #Now extract the base game.
    print("Extracting main game...")
    findCats(dataDir,patchDir,readCat)
    dumpRoot(dataDir,patchDir,targetDirectory)

if not os.path.isdir(targetDirectory):
    print("Nothing was extracted, did you set input path correctly?")
    sys.exit(1)

print("Writing EBX GUID table...")
ebx.writeGuidTable(targetDirectory)

print ("Writing RES table...")
res.writeResTable(targetDirectory)

payload.zstdCleanup()
