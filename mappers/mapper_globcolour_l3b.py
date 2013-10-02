# Name:        mapper_globcolour_l3b
# Purpose:     Mapping for GLOBCOLOUR L3B data
# Authors:     Anton Korosov
# Licence:     This file is part of NANSAT. You can redistribute it or modify
#              under the terms of GNU General Public License, v.3
#              http://www.gnu.org/licenses/gpl-3.0.html
import glob
import os.path

from scipy.io.netcdf import netcdf_file
import numpy as np
import matplotlib.pyplot as plt


from vrt import VRT, GeolocationArray
from globcolour import Globcolour

class Mapper(VRT, Globcolour):
    ''' Create VRT with mapping of WKV for MERIS Level 2 (FR or RR)'''

    def __init__(self, fileName, gdalDataset, gdalMetadata, latlonGrid=None, **kwargs):

        ''' Create MER2 VRT

        Parameters
        -----------
        fileName : string
        gdalDataset : gdal dataset
        gdalMetadata : gdal metadata
        latlonGrid : numpy 2 layered 2D array with lat/lons of desired grid
        '''
        # test if input files is GLOBCOLOUR L3B
        iDir, iFile = os.path.split(fileName)
        iFileName, iFileExt = os.path.splitext(iFile)
        print 'idir:', iDir, iFile, iFileName[0:5], iFileExt[0:8]
        assert iFileName[0:4] == 'L3b_' and iFileExt == '.nc'

        # define shape of GLOBCOLOUR grid
        GLOBCOLOR_ROWS = 180 * 24
        GLOBCOLOR_COLS = 360 * 24

        # define lon/lat grids for projected var
        if latlonGrid is None:
            #latlonGrid = np.mgrid[90:-90:4320j, -180:180:8640j].astype('float16')
            #latlonGrid = np.mgrid[80:50:900j, -10:30:1200j].astype('float16')
            latlonGrid = np.mgrid[47:39:300j, 25:45:500j].astype('float32')
            # create empty VRT dataset with geolocation only
            VRT.__init__(self, lon=latlonGrid[1], lat=latlonGrid[0])

        # get list of similar (same date) files in the directory
        simFilesMask = os.path.join(iDir, iFileName[0:30] + '*')
        simFiles = glob.glob(simFilesMask)
        print 'simFilesMask, simFiles', simFilesMask, simFiles

        metaDict = []
        self.varVRTs = []
        for simFile in simFiles:
            print 'simFile', simFile
            f = netcdf_file(simFile)

            # get iBinned, index for converting from binned into GLOBCOLOR-grid
            colBinned = f.variables['col'][:]
            rowBinned = f.variables['row'][:]
            iBinned = colBinned.astype('uint32') + (rowBinned.astype('uint32') - 1) * GLOBCOLOR_COLS
            colBinned = None
            rowBinned = None
            
            # get iRawPro, index for converting from GLOBCOLOR-grid to latlonGrid
            yRawPro = np.rint(1 + (GLOBCOLOR_ROWS - 1) * (latlonGrid[0] + 90) / 180)
            lon_step_Mat = 1 / np.cos(np.pi * latlonGrid[0] / 180.) / 24.
            xRawPro = np.rint(1 + (latlonGrid[1] + 180) / lon_step_Mat)
            iRawPro = xRawPro + (yRawPro - 1) * GLOBCOLOR_COLS
            iRawPro[iRawPro < 0] = 0
            iRawPro = np.rint(iRawPro).astype('uint32')
            yRawPro = None
            xRawPro = None
            
            for varName in f.variables:
                # find variable with _mean, eg CHL1_mean
                if '_mean' in varName:
                    break

            # read binned data
            varBinned = f.variables[varName][:]

            # convert to GLOBCOLOR grid
            varRawPro = np.zeros([GLOBCOLOR_ROWS, GLOBCOLOR_COLS], 'float32')
            varRawPro.flat[iBinned] = varBinned

            # convert to latlonGrid
            varPro = varRawPro.flat[iRawPro.flat[:]].reshape(iRawPro.shape)
            #plt.imshow(varPro);plt.colorbar();plt.show()

            # add VRT with array with data from projected variable
            self.varVRTs.append(VRT(array=varPro))

            # get WKV
            if varName in self.varname2wkv:
                varWKV = self.varname2wkv[varName]
                    
                    
                # add metadata to the dictionary
                metaEntry = {
                    'src': {'SourceFilename': self.varVRTs[-1].fileName,
                            'SourceBand':  1},
                    'dst': {'wkv': varWKV, 'original_name': varName}}

                # add wavelength for nLw
                if 'Fully normalised water leaving radiance' in f.variables[varName].long_name:
                    simWavelength = varName.split('L')[1].split('_mean')[0]
                    metaEntry['dst']['suffix'] = simWavelength
                    metaEntry['dst']['wavelength'] = simWavelength
                
                metaDict.append(metaEntry)
    

        # add bands with metadata and corresponding values to the empty VRT
        self._create_bands(metaDict)
