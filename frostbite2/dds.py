from struct import pack,unpack

class DDS_HEADER:
    def __init__(self,tex):
        self.dwMagic=b"DDS "
        self.dwSize=124
        self.dwFlags=0x1|0x2|0x4|0x1000
        if tex.type==2: self.dwFlags|=0x800000
        if tex.numMipMaps>1: self.dwFlags|=0x20000
        self.dwHeight=tex.height
        self.dwWidth=tex.width
        self.dwPitchOrLinearSize=0
        self.dwDepth=tex.depth if tex.type==2 else 1
        self.dwMipMapCount=tex.numMipMaps
        self.dwReserved1=bytes(11*0x04)
        self.ddspf=DDS_PIXELFORMAT(tex)
        self.dwCaps=0x1000
        if tex.type in [1,2]: self.dwCaps|=0x8
        if tex.numMipMaps>1: self.dwCaps|=0x8|0x400000
        self.dwCaps2=0
        if tex.type==1:
            #Cubemap
            self.dwCaps2|=0x200
            for i in range(6):
                self.dwCaps2|=(1<<(10+i))
        elif tex.type==2:
            #Volume texture
            self.dwCaps2|=0x200000
        self.dwCaps3=0
        self.dwCaps4=0
        self.dwReserved2=0

    def encode(self):
        data=pack("<4s7I44s",
                    self.dwMagic,
                    self.dwSize,
                    self.dwFlags,
                    self.dwHeight,
                    self.dwWidth,
                    self.dwPitchOrLinearSize,
                    self.dwDepth,
                    self.dwMipMapCount,
                    self.dwReserved1)
        data+=self.ddspf.encode()
        data+=pack("<5I",
                    self.dwCaps,
                    self.dwCaps2,
                    self.dwCaps3,
                    self.dwCaps4,
                    self.dwReserved2)

        return data

class DDS_PIXELFORMAT:
    def __init__(self,tex):
        self.dwSize=32
        enum=getFormatEnum(tex.version)
        values=remapFormat(enum,tex.format)
        self.dwFlags=values[0]

        if self.dwFlags & 0x04:
            self.dwFourCC=values[1]
            self.dwRGBBitCount=0
            self.dwRBitMask=0
            self.dwGBitMask=0
            self.dwBBitMask=0
            self.dwABitMask=0
        else:
            self.dwFourCC=bytes(4)
            self.dwRGBBitCount=values[1]
            self.dwRBitMask=values[2]
            self.dwGBitMask=values[3]
            self.dwBBitMask=values[4]
            self.dwABitMask=values[5]

    def encode(self):
        return pack("<2I4s5I",
                    self.dwSize,
                    self.dwFlags,
                    self.dwFourCC,
                    self.dwRGBBitCount,
                    self.dwRBitMask,
                    self.dwGBitMask,
                    self.dwBBitMask,
                    self.dwABitMask)

def getFormatEnum(version):
    if version==0x0a:
        return TextureFormat_v10
    elif version==0x6e:
        return TextureFormat_v110
    else:
        return None

#Info on DDS_PIXELFORMAT struct presets taken from here:
# https://github.com/microsoft/DirectXTex/blob/master/DirectXTex/DirectXTexDDS.cpp
# https://github.com/microsoft/DirectXTex/blob/master/DirectXTex/DDS.h
def remapFormat(fmt,val):
    formatMap = {
        fmt.TextureFormat_DXT1:             (0x04,b"DXT1"),
        fmt.TextureFormat_DXT1A:            (0x04,b"DXT1"),
        fmt.TextureFormat_DXT3:             (0x04,b"DXT3"),
        fmt.TextureFormat_DXT5:             (0x04,b"DXT5"),
        fmt.TextureFormat_DXT5A:            (0x04,b"ATI1"),
        fmt.TextureFormat_DXN:              (0x04,b"ATI2"),
        fmt.TextureFormat_RGB565:           (0x40,16,0xf800,0x07e0,0x001f,0),
        fmt.TextureFormat_RGB888:           (0x40,24,0xff0000,0x00ff00,0x0000ff,0),
        fmt.TextureFormat_ARGB1555:         (0x41,16,0x7c00,0x03e0,0x001f,0x8000),
        fmt.TextureFormat_ARGB4444:         (0x41,16,0x0f00,0x00f0,0x000f,0xf000),
        fmt.TextureFormat_ARGB8888:         (0x41,32,0x00ff0000,0x0000ff00,0x000000ff,0xff000000),
        fmt.TextureFormat_L8:               (0x20000,8,0xff,0,0,0),
        fmt.TextureFormat_L16:              (0x20000,16,0xffff,0,0,0),
        fmt.TextureFormat_ABGR16:           (0x04,b"\x24\0\0\0"),
        fmt.TextureFormat_ABGR16F:          (0x04,b"\x71\0\0\0"),
        fmt.TextureFormat_ABGR32F:          (0x04,b"\x74\0\0\0"),
        fmt.TextureFormat_NormalDXN:        (0x04,b"ATI2"),
        fmt.TextureFormat_NormalDXT1:       (0x04,b"DXT1"),
        fmt.TextureFormat_NormalDXT5:       (0x04,b"DXT5"),
        fmt.TextureFormat_NormalDXT5RGA:    (0x04,b"DXT5"),
    }

    if val not in formatMap or val==0xFFFFFFFF:
        return None

    return formatMap[val]

#Standard FB2 list, found in BF3 debug strings
class TextureFormat_v10:
    TextureFormat_DXT1 = 0x0
    TextureFormat_DXT3 = 0x1
    TextureFormat_DXT5 = 0x2
    TextureFormat_DXT5A = 0x3
    TextureFormat_DXN = 0x4
    TextureFormat_RGB565 = 0x5
    TextureFormat_RGB888 = 0x6
    TextureFormat_ARGB1555 = 0x7
    TextureFormat_ARGB4444 = 0x8
    TextureFormat_ARGB8888 = 0x9
    TextureFormat_L8 = 0x0A
    TextureFormat_L16 = 0x0B
    TextureFormat_ABGR16 = 0x0C
    TextureFormat_ABGR16F = 0x0D
    TextureFormat_ABGR32F = 0x0E
    TextureFormat_R16F = 0x0F
    TextureFormat_R32F = 0x10
    TextureFormat_NormalDXN = 0x11
    TextureFormat_NormalDXT1 = 0x12
    TextureFormat_NormalDXT5 = 0x13
    TextureFormat_NormalDXT5RGA = 0x14
    TextureFormat_RG8 = 0x15
    TextureFormat_GR16 = 0x16
    TextureFormat_GR16F = 0x17
    TextureFormat_D16 = 0x18
    TextureFormat_D24S8 = 0x19
    TextureFormat_D24FS8 = 0x1A
    TextureFormat_D32F = 0x1B
    TextureFormat_ABGR32 = 0x1C
    TextureFormat_GR32F = 0x1D
    TextureFormat_A2R10G10B10 = 0x1E

    TextureFormat_DXT1A = 0xFFFFFFFF

    def __init__(self):
        pass

#Found in MOH:WF
class TextureFormat_v110:
    TextureFormat_DXT1 = 0x0
    TextureFormat_DXT1A = 0x1
    TextureFormat_DXT3 = 0x2
    TextureFormat_DXT5 = 0x3
    TextureFormat_DXT5A = 0x4
    TextureFormat_DXN = 0x5
    TextureFormat_RGB565 = 0x6
    TextureFormat_RGB888 = 0x7
    TextureFormat_ARGB1555 = 0x8
    TextureFormat_ARGB4444 = 0x9
    TextureFormat_ARGB8888 = 0x0A
    TextureFormat_L8 = 0x0B
    TextureFormat_L16 = 0x0C
    TextureFormat_ABGR16 = 0x0D
    TextureFormat_ABGR16F = 0x0E
    TextureFormat_ABGR32F = 0x0F
    TextureFormat_R16F = 0x10
    TextureFormat_R32F = 0x11
    TextureFormat_NormalDXN = 0x12
    TextureFormat_NormalDXT1 = 0x13
    TextureFormat_NormalDXT5 = 0x14
    TextureFormat_NormalDXT5RGA = 0x15
    TextureFormat_RG8 = 0x16
    TextureFormat_GR16 = 0x17
    TextureFormat_GR16F = 0x18
    TextureFormat_D16 = 0x19
    TextureFormat_D24S8 = 0x1A
    TextureFormat_D24FS8 = 0x1B
    TextureFormat_D32F = 0x1C
    TextureFormat_ABGR32 = 0x1D
    TextureFormat_GR32F = 0x1E
    TextureFormat_A2R10G10B10 = 0x1F

    def __init__(self):
        pass
