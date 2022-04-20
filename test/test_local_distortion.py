'''
Created on Sep 26, 2018

@author: u0490822
'''
import unittest

import os
import os.path
import pickle
import nornir_pools
import nornir_shared.plot
import nornir_shared.plot as plot
import numpy as np
import nornir_imageregistration 

from nornir_imageregistration.local_distortion_correction import _RunRefineTwoImagesIteration, RefineStosFile
from nornir_imageregistration.alignment_record import EnhancedAlignmentRecord
import nornir_imageregistration.assemble

import nornir_imageregistration.scripts.nornir_stos_grid_refinement

from nornir_shared.files import try_locate_file

from . import setup_imagetest
from . import test_arrange
import local_distortion_correction
from build.lib.nornir_imageregistration.files import stosfile

# class TestLocalDistortion(setup_imagetest.TransformTestBase):
# 
#     @property
#     def TestName(self):
#         return "GridRefinement"
#     
#     def setUp(self):
#         super(TestLocalDistortion, self).setUp()
#         return 
# 
# 
#     def tearDown(self):
#         super(TestLocalDistortion, self).tearDown()
#         return
# 
# 
#     def testRefineMosaic(self):
#         '''
#         This is a test for the refine mosaic feature which is not fully implemented
#         '''
#         tilesDir = self.GetTileFullPath()
#         mosaicFile = self.GetMosaicFile("Translated")
#         mosaic = nornir_imageregistration.mosaic.Mosaic.LoadFromMosaicFile(mosaicFile)
#         mosaic.RefineMosaic(tilesDir, usecluster=False)
#         pass
    
class TestSliceToSliceRefinement(setup_imagetest.TransformTestBase, setup_imagetest.PickleHelper):

    def __init__(self, methodName='runTest'):
        self._TestName = 'SliceToSliceRefinement'
        
        #if methodName.startswith('test'):
            #self._TestName = methodName[len('test'):]
        #else:
            #self._TestName = methodName
            
        setup_imagetest.TransformTestBase.__init__(self, methodName=methodName)
        
    @property
    def TestName(self):
        return self._TestName
    
    def setUp(self):
        super(TestSliceToSliceRefinement, self).setUp()
        return 

    def tearDown(self):
        super(TestSliceToSliceRefinement, self).tearDown()
        return
    
    @property
    def ImageDir(self):
        return os.path.join(self.ImportedDataPath, '..\\..\\Images\\')
    
    #def testStosRefinementRC1_258(self): 
        ##self.TestName = "StosRefinementRC1_258"
        #stosFile = self.GetStosFile("0258-0257_grid_16.stos")
        #self.RunStosRefinement(stosFile, ImageDir=self.TestInputDataPath, SaveImages=False, SavePlots=True)
    
#     def testStosRefinementRC2_162(self):
#         SaveImages = False
#         SavePlots = True
#         self.TestName = "StosRefinementRC2_162"
#         stosFile = self.GetStosFile("0164-0162_brute_32")
#         self.RunStosRefinement(stosFile, self.ImageDir, SaveImages=False, SavePlots=True)
#     
    def testStosRefinementRC2_617(self):
        #self.TestName = "StosRefinementRC2_617"
        stosFilePath = self.GetStosFilePath("StosRefinementRC2_617", "0617-0618_brute_32_pyre")
        #self.RunStosRefinement(stosFilePath, ImageDir=os.path.dirname(stosFilePath), SaveImages=True, SavePlots=True)
#         RefineStosFile(InputStos=stosFile, 
#                        OutputStosPath=os.path.join(self.TestOutputPath, 'Final.stos'),
#                        num_iterations=10,
#                        cell_size=(128,128),
#                        grid_spacing=(128,128),
#                        angles_to_search=[-2.5, 0, 2.5],
#                        min_travel_for_finalization=0.5,
#                        min_alignment_overlap=0.5,
#                        SaveImages=True,
#                        SavePlots=True)
        
    def testStosRefinementRC2_1034(self):
        #self.TestName = "StosRefinementRC2_617"
        stosFilePath = self.GetStosFilePath("StosRefinementRC2_1034","1034-1032_ctrl-TEM_Leveled_map-TEM_Leveled_original.stos")
        #self.RunStosRefinement(stosFilePath, ImageDir=os.path.dirname(stosFilePath), SaveImages=True, SavePlots=True)
#         RefineStosFile(InputStos=stosFile, 
#                        OutputStosPath=os.path.join(self.TestOutputPath, 'Final.stos'),
#                        num_iterations=10,
#                        cell_size=(128,128),
#                        grid_spacing=(128,128),
#                        angles_to_search=[-2.5, 0, 2.5],
#                        min_travel_for_finalization=0.5,
#                        min_alignment_overlap=0.5,
#                        SaveImages=True,
#                        SavePlots=True)

    def testStosRefinementRC2_1034_Mini(self):
        #self.TestName = "StosRefinementRC2_617"
        stosFilePath = self.GetStosFilePath("StosRefinementRC2_1034_Mini","1032-1034_brute_32_pyre_crude_across.stos")
        self.RunStosRefinement(stosFilePath, ImageDir=os.path.dirname(stosFilePath), SaveImages=True, SavePlots=True)
#         RefineStosFile(InputStos=stosFile, 
#                        OutputStosPath=os.path.join(self.TestOutputPath, 'Final.stos'),
#                        num_iterations=10,
#                        cell_size=(128,128),
#                        grid_spacing=(128,128),
#                        angles_to_search=[-2.5, 0, 2.5],
#                        min_travel_for_finalization=0.5,
#                        min_alignment_overlap=0.5,
#                        SaveImages=True,
#                        SavePlots=True)
    
    def RunStosRefinement(self, stosFilePath, ImageDir=None, SaveImages=False, SavePlots=True):
        '''
        This is a test for the refine mosaic feature which is not fully implemented
        '''
          
        #stosFile = self.GetStosFile("0164-0162_brute_32")
        #stosFile = self.GetStosFile("0617-0618_brute_64")
        stosObj = nornir_imageregistration.files.StosFile.Load(stosFilePath)
        #stosObj.Downsample = 64.0
        #stosObj.Scale(2.0)
        #stosObj.Save(os.path.join(self.TestOutputPath, "0617-0618_brute_32.stos"))
        
        fixedImage = stosObj.ControlImageFullPath
        warpedImage = stosObj.MappedImageFullPath
        
        if ImageDir is not None:
            fixedImage = os.path.join(ImageDir, stosObj.ControlImageFullPath)
            warpedImage = os.path.join(ImageDir, stosObj.MappedImageFullPath)
            
        fixedImageData = nornir_imageregistration.ImageParamToImageArray(fixedImage, dtype=np.float16)
        warpedImageData = nornir_imageregistration.ImageParamToImageArray(warpedImage, dtype=np.float16)
              
        stosTransform = nornir_imageregistration.transforms.factory.LoadTransform(stosObj.Transform, 1)
        
        unrefined_image_path = os.path.join(self.TestOutputPath, 'unrefined_transform.png')
        
#        if not os.path.exists(unrefined_image_path):        
#            unrefined_warped_image = nornir_imageregistration.assemble.TransformStos(stosTransform, 
#                                                                                     fixedImage=fixedImage,
#                                                                                     warpedImage=warpedImage)
#            nornir_imageregistration.SaveImage(unrefined_image_path, unrefined_warped_image, bpp=8)
#        else:
#            unrefined_warped_image = nornir_imageregistration.LoadImage(unrefined_image_path)
         
        
        num_iterations = 10
        
        cell_size=np.asarray((128, 128),dtype=np.int32)
        grid_spacing=(92, 92)
        
        i = 1
        
        finalized_points = {}
        
        min_percentile_included = 5.0
        
        final_pass = False
        final_pass_angles = np.linspace(-7.5, 7.5, 11)
        
        CutoffPercentilePerIteration = 10.0
        
        angles_to_search = None
        
        pool = nornir_pools.GetGlobalThreadPool()
                        
        while i <= num_iterations: 
                
            cachedFileName = '{5}_pass{0}_alignment_Cell_{2}x{1}_Grid_{4}x{3}'.format(i,cell_size[0], cell_size[1],
                                                                                         grid_spacing[0], grid_spacing[1], 
                                                                                         self.TestName)
            alignment_points = self.ReadOrCreateVariable(cachedFileName)
            
            if alignment_points is None:
                alignment_points = _RunRefineTwoImagesIteration(stosTransform,
                            fixedImageData,
                            warpedImageData,
                            os.path.join(ImageDir, stosObj.ControlMaskName),
                            os.path.join(ImageDir, stosObj.MappedMaskName),
                            cell_size=cell_size,
                            grid_spacing=grid_spacing,
                            finalized=finalized_points,
                            angles_to_search=angles_to_search,
                            min_alignment_overlap=None)
                self.SaveVariable(alignment_points, cachedFileName)
                
            print("Pass {0} aligned {1} points".format(i,len(alignment_points)))
            
            if i == 1:
                cell_size = cell_size / 2.0
                
            combined_alignment_points = alignment_points + list(finalized_points.values())
            
            percentile = 50.0 - (CutoffPercentilePerIteration * i)
            if percentile < 10.0:
                percentile = 10.0
            elif percentile > 100:
                percentile = 100
                
   #         if final_pass:
   #             percentile = 0
   
            updatedTransform = local_distortion_correction._PeakListToTransform(combined_alignment_points, percentile)
                
            if SavePlots:
                histogram_filename = os.path.join(self.TestOutputPath, 'weight_histogram_pass{0}.png'.format(i))
                nornir_imageregistration.views.PlotWeightHistogram(alignment_points, histogram_filename, cutoff=percentile/100.0)
                vector_field_filename = os.path.join(self.TestOutputPath, 'Vector_field_pass{0}.png'.format(i))
                nornir_imageregistration.views.PlotPeakList(alignment_points, list(finalized_points.values()),  vector_field_filename,
                                                          ylim=(0, fixedImageData.shape[1]),
                                                          xlim=(0, fixedImageData.shape[0]))
                                
            
            finalize_percentile = 50.0
            if finalize_percentile < 10.0:
                finalize_percentile = 10.0
            elif finalize_percentile > 100:
                finalize_percentile = 100
                
            new_finalized_points = local_distortion_correction.CalculateFinalizedAlignmentPointsMask(alignment_points,
                                                                                                     percentile=finalize_percentile,
                                                                                                     min_travel_distance=1)
             
            new_finalizations = 0
            for (ir, record) in enumerate(alignment_points): 
                if not new_finalized_points[ir]:
                    continue
                
                key = tuple(record.SourcePoint)
                if key in finalized_points:
                    continue
                
                #See if we can improve the final alignment
                refined_align_record = nornir_imageregistration.stos_brute.SliceToSliceBruteForce(record.TargetROI,
                                                                                                  record.SourceROI,
                                                                                                  AngleSearchRange=final_pass_angles,
                                                                                                  MinOverlap=0.25,
                                                                                                  SingleThread=True,
                                                                                                  Cluster=False,
                                                                                                  TestFlip=False)
                
                if refined_align_record.weight > record.weight:
                    record = nornir_imageregistration.alignment_record.EnhancedAlignmentRecord(ID=record.ID,
                                                                                 TargetPoint=record.TargetPoint,
                                                                                 SourcePoint=record.SourcePoint,
                                                                                 peak=refined_align_record.peak,
                                                                                 weight=refined_align_record.weight,
                                                                                 angle=refined_align_record.angle,
                                                                                 flipped_ud=refined_align_record.flippedud)
                 
                #Create a record that is unmoving
                finalized_points[key] =  EnhancedAlignmentRecord(record.ID, 
                                                                 TargetPoint=record.AdjustedTargetPoint,
                                                                 SourcePoint=record.SourcePoint,
                                                                 peak=np.asarray((0,0), dtype=np.float32),
                                                                 weight=record.weight, angle=0, 
                                                                 flipped_ud=record.flippedud )
                
                new_finalizations += 1
                
            print("Pass {0} has locked {1} new points, {2} of {3} are locked".format(i,
                                                                                     new_finalizations,
                                                                                     len(finalized_points), len(combined_alignment_points)))
                
             
            stosObj.Transform = updatedTransform
            stosObj.Save(os.path.join(self.TestOutputPath, "UpdatedTransform_pass{0}.stos".format(i)))
                 
            if SaveImages:   
                warpedToFixedImage = nornir_imageregistration.assemble.TransformStos(updatedTransform, fixedImage=fixedImageData, warpedImage=warpedImageData)
                 
                Delta = warpedToFixedImage - fixedImageData
                ComparisonImage = np.abs(Delta)
                ComparisonImage = ComparisonImage / ComparisonImage.max() 
                 
                
                #nornir_imageregistration.SaveImage(os.path.join(self.TestOutputPath, 'delta_pass{0}.png'.format(i)), ComparisonImage, bpp=8)
                #nornir_imageregistration.SaveImage(os.path.join(self.TestOutputPath, 'image_pass{0}.png'.format(i)), warpedToFixedImage, bpp=8)
                
                pool.add_task('delta_pass{0}.png'.format(i), nornir_imageregistration.SaveImage, os.path.join(self.TestOutputPath, 'delta_pass{0}.png'.format(i)), np.copy(ComparisonImage), bpp=8)
                pool.add_task('image_pass{0}.png'.format(i), nornir_imageregistration.SaveImage, os.path.join(self.TestOutputPath, 'image_pass{0}.png'.format(i)), np.copy(warpedToFixedImage), bpp=8)
     
            #nornir_imageregistration.core.ShowGrayscale([fixedImageData, unrefined_warped_image, warpedToFixedImage, ComparisonImage])
             
            i = i + 1
            
            #Build a final transform using only finalized points
            #stosTransform = updatedTransform
            stosTransform = local_distortion_correction._PeakListToTransform(list(finalized_points.values()), percentile)
            
            if final_pass:
                break
            
            if i == num_iterations:
                final_pass = True
                angles_to_search = final_pass_angles
            
            #If we've locked 10% of the points and have not locked any new ones we are done
            if len(finalized_points) > len(combined_alignment_points) * 0.1 and new_finalizations == 0:
                final_pass = True
                angles_to_search = final_pass_angles
            
            #If we've locked 90% of the points we are done
            if len(finalized_points) > len(combined_alignment_points) * 0.9:
                final_pass = True
                angles_to_search = final_pass_angles
            
        #Convert the transform to a grid transform and persist to disk
        stosObj.Transform = local_distortion_correction.ConvertTransformToGridTransform(stosObj.Transform, source_image_shape=warpedImageData.shape, cell_size=cell_size, grid_spacing=grid_spacing)
        stosObj.Save(os.path.join(self.TestOutputPath, "Final_Transform.stos") )
        return
      
    def testGridRefineScript(self):
        stosFile = self.GetStosFilePath("StosRefinementRC2_617", "0617-0618_brute_32_pyre")
        args = ['-input', stosFile,
                '-output', os.path.join(self.TestOutputPath,'scriptTestResult.stos'),
                '-min_overlap', '0.5',
                '-grid_spacing', '128,128',
                '-it', '1',
                '-c','256,256',
                '-angles','0',
                '-travel_cutoff','0.5']
        
        #nornir_imageregistration.scripts.nornir_stos_grid_refinement.Execute(args)
        return
    
    def _rotate_points(self, points, rotcenter, rangle):
        
        t = nornir_imageregistration.transforms.Rigid(target_offset=(0,0), source_rotation_center=rotcenter, angle=rangle)
        return t.Transform(points)
    
    def testTransformReductionToRigidTransform(self):
        '''
        Takes the control points of a transform and converts each point to a rigid transform that approximates the offset and angle centered at that point
        '''
        
        #A set of control points offset by (10,10)
        InitialTargetPoints = np.asarray([[0, 0],
                                  [10, 0],
                                  [0, 10],
                                  [10, 10]], dtype=np.float64)
        
        angle = -30.0
        rangle = (angle / 180.0) * np.pi
        
        CalculatedSourcePoints = self._rotate_points(InitialTargetPoints, rotcenter=(0,0), rangle=rangle)
        
        #Optional offset to add as an additional test
        CalculatedSourcePoints += np.array((-1,4))
        
        controlPoints = np.hstack((InitialTargetPoints, CalculatedSourcePoints))
        reference_transform = nornir_imageregistration.transforms.MeshWithRBFFallback(controlPoints)

        ValidationTestPoints = reference_transform.InverseTransform(InitialTargetPoints)
        np.testing.assert_allclose(ValidationTestPoints, CalculatedSourcePoints)
        
        #OK, check that the rigid transforms returned for the InitialTargetPoints perfectly match our reference_transform
        local_rigid_transforms = local_distortion_correction.ApproximateRigidTransform(reference_transform, InitialTargetPoints)
        
        for i, t in enumerate(local_rigid_transforms):
            test_source_points = t.InverseTransform(InitialTargetPoints)
            np.testing.assert_allclose(test_source_points, CalculatedSourcePoints, atol=.001, err_msg="Inverse Transform Iteration {0}".format(i))
            
            test_target_points = t.Transform(CalculatedSourcePoints)
            np.testing.assert_allclose(test_target_points, InitialTargetPoints, atol=.001, err_msg="Transform Iteration {0}".format(i))
            
        return
        
    
    def testAlignmentRecordsToTransforms(self):
        '''
        Converts a set of alignment records into a transform
        '''
        
        #A set of control points offset by (10,10)
        InitialTransformPoints = [[0, 0, 10, 10],
                                  [10, 0, 20, 10],
                                  [0, 10, 10, 20],
                                  [10, 10, 20, 20]]
        T = nornir_imageregistration.transforms.MeshWithRBFFallback(InitialTransformPoints)
        
        transformed = T.InverseTransform(T.TargetPoints)
        self.assertTrue(np.allclose(T.SourcePoints, transformed), "Transform could not map the initial input to the test correctly")
        
        transform_testPoints = [[-1,-2]] 
        expectedOutOfBounds = np.asarray([[9,8]], dtype=np.float64) 
        transformed_out_of_bounds = T.InverseTransform(transform_testPoints)
        self.assertTrue(np.allclose(transformed_out_of_bounds, expectedOutOfBounds), "Transform could not map the initial input to the test correctly")
         
        inverse_transformed_out_of_bounds = T.Transform(expectedOutOfBounds)
        self.assertTrue(np.allclose(transform_testPoints, inverse_transformed_out_of_bounds), "Transform could not map the initial input to the test correctly")
        
        #Create fake alignment results requiring us to shift the transform up one
        a = EnhancedAlignmentRecord((0,0), (0,0), (10,10), (1,0), 1.5)
        b = EnhancedAlignmentRecord((1,0), (10,0), (20,10), (1,0), 2.5)
        c = EnhancedAlignmentRecord((0,1), (0,10), (10,20), (1,0), 3)
        d = EnhancedAlignmentRecord((1,1), (10,10), (20,20), (1,0), 2)
        
        records = [a,b,c,d]
        
        ##Transforming the adjusted fixed point with the old transform generates an incorrect result
        for r in records:
            r.CalculatedWarpedPoint = T.InverseTransform(r.AdjustedTargetPoint)
        ########
        
        #If this is failing check that at least three records make it past the filter criteria
        transform = local_distortion_correction._PeakListToTransform(records)
        
        test1 = np.asarray(((0,0),(5,5),(10,10)))
        expected1 = np.asarray(((9,10),(14,15),(19,20))) 
        actual1 = transform.InverseTransform(test1)
        
        self.assertTrue(np.allclose(expected1, actual1))
         
        records2 = []
        ####Begin 2nd pass.  Pretend we need to shift every over one
        for iRow in range(0,transform.SourcePoints.shape[0]):
            r = EnhancedAlignmentRecord(records[iRow].ID, 
                                        transform.TargetPoints[iRow,:], 
                                        transform.SourcePoints[iRow,:], 
                                        (0,-1),
                                        5.0)
            records2.append(r)
            
        
        transform2 = local_distortion_correction._PeakListToTransform(records2)
        test2 = np.asarray(((0,0),(5,5),(10,10)))
        expected2 = np.asarray(((9,11),(14,16),(19,21))) 
        actual2 = transform2.InverseTransform(test2)
        
        self.assertTrue(np.allclose(expected2, actual2))
        
        pass


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()