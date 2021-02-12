import os
from os.path import exists

WARN_ABORT = "\n\tPress ctrl+x to abort or any key to continue.\n"


# will prompt user for an input, adding two blank lines before, one blank line after, prefix the prompt with >> and indent the cursor. 
def formattedInputQuery(query) :
    return input("\n\n" + query + "\n  >>\t")

# will surround the output with twoblank lines.
def formattedOutput(str) :
    print("\n", str, "\n")

# Exception-proof checking if a given targetPath exists. Optional boolean checks for existance of "Data" subfolder.
def isValidDir(targetPath, checkForDataSubfolder=False): 
    try:
        if (len(targetPath) > 0 and exists(targetPath)) :
            # if we're supposed to be checking, do check, otherwise, return true
            return (not checkForDataSubfolder) or exists(targetPath + "\\Data")
    except:
        return False

# Helper method for path creation. Will stop script if directory does not exist. 
# create: If the path does not exist, it will be created (makedirs - including parent dirs, if necessary)
# warnNotEmpty: If the path does exist and is a non-empty folder, print a console warning.
def getOrCreatePathWithQuery(query, create=False, warnNotEmpty=False): 
        
    targetPath = formattedInputQuery(query)
    if not exists(targetPath):
        if not create: 
            formattedOutput("Error: directory " + targetPath + " does not exist. Terminating.")
            raise SystemExit
        os.makedirs(targetPath)
    elif warnNotEmpty and os.listdir(targetPath) : 
        formattedOutput("Warning: target directory is not empty." + WARN_ABORT)
    return targetPath

        
# Validates existance of game directory and checks for subfolder Data
def getGamePath(path):
    if isValidDir(path, True):
        return path
     
    targetPath = getOrCreatePathWithQuery("Please enter path to game directory (must contain Data folder)")    
    if isValidDir(targetPath, True):
        return targetPath
        
    formattedOutput("Error: game directory " + targetPath + " invalid.\n", "Folder does not exist or does not contain subfolder 'Data'.\n" , "Script will terminate.")    
    raise SystemExit

# Checks for or creates extraction path. Put into own method to avoid string duplication.    
def getExtractPath(path):
    if (isValidDir(path)):
        return path        
    return getOrCreatePathWithQuery("Please enter path to target directory (should not be in your documents)", True, True)    
    


# Helper method for ebxTo*-methods to read a relative subdirectory
def getRelativePathWithQuery(path, relativePath, query):
    targetPath = path + "\\" + relativePath
    if (isValidDir(targetPath)):
        return targetPath
    relativePath =  formattedInputQuery(query)
    if len(relativePath) > 0: 
        targetPath = path + "\\" + relativePath
        if (isValidDir(targetPath)) :
            return relativePath
        formattedInputQuery("Warning: invalid path under \n\t"+ targetPath + WARN_ABORT )
    
    return ""    