'''
Created on Mar 21, 2013

@author: u0490822
'''
import cProfile
import glob
import logging
import os
import pickle
import shutil
import unittest

import six

import nornir_pools
from nornir_shared.misc import SetupLogging
import numpy as np


class PickleHelper(object):
         
    @property
    def TestCachePath(self):
        '''Contains cached files from previous test runs, such as database query results.
           Entries in this cache should have a low probablility of changing and breaking tests'''
        if 'TESTOUTPUTPATH' in os.environ:
            TestOutputDir = os.environ["TESTOUTPUTPATH"]
            return os.path.join(TestOutputDir, "Cache", self.classname)
        else:
            self.fail("TESTOUTPUTPATH environment variable should specify test output directory")

        return None
    
    @staticmethod
    def _ensure_pickle_extension(path):
        (_, ext) = os.path.splitext(path)
        if ext != '.pickle':
            path = os.path.join(path, '.pickle')
        return path 
    
    def SaveVariable(self, var, path):
        path = PickleHelper._ensure_pickle_extension(path)
        
        fullpath = os.path.join(self.TestCachePath, path)

        if not os.path.exists(os.path.dirname(fullpath)):
            os.makedirs(os.path.dirname(fullpath))

        with open(fullpath, 'wb') as filehandle:
            print("Saving: " + fullpath)
            pickle.dump(var, filehandle, protocol=pickle.HIGHEST_PROTOCOL)
            

    def ReadOrCreateVariable(self, varname, createfunc=None, **kwargs):
        '''Reads variable from disk, call createfunc if it does not exist'''

        var = None
        if hasattr(self, varname):
            var = getattr(self, varname)

        if var is None:
            path = os.path.join(self.TestCachePath, varname + ".pickle")
            path = PickleHelper._ensure_pickle_extension(path)
            if os.path.exists(path):
                with open(path, 'rb') as filehandle:
                    try:
                        var = pickle.load(filehandle)
                    except:
                        var = None
                        print("Unable to load graph from pickle file: " + path)

            if var is None and not createfunc is None:
                var = createfunc(**kwargs)
                self.SaveVariable(var, path)

        return var


class TestBase(unittest.TestCase):

    @property
    def classname(self):
        clsstr = str(self.__class__.__name__)
        return clsstr


    @property
    def TestInputPath(self):
        if 'TESTINPUTPATH' in os.environ:
            TestInputDir = os.environ["TESTINPUTPATH"]
            self.assertTrue(os.path.exists(TestInputDir), "Test input directory specified by TESTINPUTPATH environment variable does not exist")
            return TestInputDir
        else:
            self.fail("TESTINPUTPATH environment variable should specfify input data directory")

        return None

    @property
    def TestOutputPath(self):
        if 'TESTOUTPUTPATH' in os.environ:
            TestOutputDir = os.environ["TESTOUTPUTPATH"]
            return os.path.join(TestOutputDir, self.classname, self._testMethodName)
        else:
            self.fail("TESTOUTPUTPATH environment variable should specfify input data directory")

        return None

    @property
    def TestLogPath(self):
        #if 'TESTOUTPUTPATH' in os.environ:
        #TestOutputDir = os.environ["TESTOUTPUTPATH"]
            return os.path.join(self.TestOutputPath, "Logs")
        #else:
        #self.fail("TESTOUTPUTPATH environment variable should specfify input data directory")

        #return None

    @property
    def TestProfilerOutputPath(self):
        return os.path.join(self.TestOutputPath, self._testMethodName + '.profile')

    def setUp(self):
        self.VolumeDir = self.TestOutputPath

        # Remove output of earlier tests

        try:
            if os.path.exists(self.VolumeDir):
                shutil.rmtree(self.VolumeDir)
        except:
            pass
        
        try:
            os.makedirs(self.VolumeDir, exist_ok=True)
        except PermissionError as e:
            print(str(e))
            pass
            

        self.profiler = None

        if 'PROFILE' in os.environ:
            os.environ['PROFILE'] = self.TestOutputPath #Overwrite the value with the directory we want the profile data saved in
            self.profiler = cProfile.Profile()
            self.profiler.enable()

        SetupLogging(Level=logging.INFO)
        self.Logger = logging.getLogger(self.classname)

    def tearDown(self):
         
        nornir_pools.ClosePools()
        
        if not self.profiler is None:
            self.profiler.dump_stats(self.TestProfilerOutputPath)

        unittest.TestCase.tearDown(self)


class ImageTestBase(TestBase):

    def GetImagePath(self, ImageFilename):
        return os.path.join(self.ImportedDataPath, ImageFilename)
    
    @property
    def TestOutputPath(self):
        return os.path.join(super(ImageTestBase, self).TestOutputPath, self.id().split('.')[-1])

    def setUp(self):
        self.ImportedDataPath = os.path.join(self.TestInputPath, "Images")

        super(ImageTestBase, self).setUp()


class TransformTestBase(TestBase):

    @property
    def TestName(self):
        raise NotImplementedError("Test should override TestName property")
    
    @property
    def TestInputDataPath(self):
        return os.path.join(self.TestInputPath, 'Transforms', self.TestName)
    
    @property
    def TestOutputPath(self):
        return os.path.join(super(TransformTestBase, self).TestOutputPath, self.id().split('.')[-1])

    def GetMosaicFiles(self):
        return glob.glob(os.path.join(self.ImportedDataPath, self.TestName, "*.mosaic"))
    
    def GetMosaicFile(self, filenamebase):
        (base, ext) = os.path.splitext(filenamebase)
        if ext is None or len(ext) == 0:
            filenamebase = filenamebase + '.mosaic'
            
        return glob.glob(os.path.join(self.TestInputDataPath, filenamebase + ".mosaic"))[0]
    
    def GetStosFiles(self, *args):
        return glob.glob(os.path.join(self.TestInputDataPath, *args, "*.stos"))
    
    def GetStosFilePath(self, *args): 
        '''Return a .stos file at a specific path'''
        filenamebase = args[-1]
        (base, ext) = os.path.splitext(filenamebase)
        if ext is None or len(ext) == 0:
            filenamebase = filenamebase + '.stos' 
            
        path = os.path.join(self.TestInputDataPath, *args[0:-1], filenamebase)
        self.assertTrue(os.path.exists(path), f'{path} is missing')
        
        return path

    def GetTileFullPath(self, downsamplePath=None):
        if downsamplePath is None:
            downsamplePath = "001"

        return os.path.join(self.TestInputDataPath, "Leveled", "TilePyramid", downsamplePath)

    def setUp(self):
        self.ImportedDataPath = os.path.join(self.TestInputPath, "Transforms", "Mosaics")
        
        if not os.path.exists(self.TestOutputPath):
            if six.PY3:
                os.makedirs(self.TestOutputPath, exist_ok=True)
            else:
                if not os.path.exists(self.TestOutputPath):
                    os.makedirs(self.TestOutputPath)

        super(TransformTestBase, self).setUp()
        
def array_distance(array):
    '''Convert an Mx2 array into a Mx1 array of euclidean distances'''
    if array.ndim == 1:
        return np.sqrt(np.sum(array ** 2)) 
    
    return np.sqrt(np.sum(array ** 2, 1))


if __name__ == "__main__":
    # import syssys.argv = ['', 'Test.testName']
    unittest.main()
