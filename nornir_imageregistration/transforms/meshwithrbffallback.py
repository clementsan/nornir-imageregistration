'''
Created on Oct 18, 2012

@author: Jamesan
'''

import math

import nornir_imageregistration 
from nornir_imageregistration.transforms.rbftransform import RBFWithLinearCorrection
import numpy
import scipy.interpolate

import nornir_pools 
from .triangulation import Triangulation

from . import utils, NumberOfControlPointsToTriggerMultiprocessing


class MeshWithRBFFallback(Triangulation):
    '''
    classdocs
    '''
    
    def __getstate__(self):
        
        odict = super(MeshWithRBFFallback, self).__getstate__()
        odict['_ReverseRBFInstance'] = self._ReverseRBFInstance
        odict['_ForwardRBFInstance'] = self._ForwardRBFInstance
        return odict

    def __setstate__(self, dictionary):
        super(MeshWithRBFFallback, self).__setstate__(dictionary)

    @property
    def ReverseRBFInstance(self):
        if self._ReverseRBFInstance is None:
            self._ReverseRBFInstance = RBFWithLinearCorrection(self.TargetPoints, self.SourcePoints)

        return self._ReverseRBFInstance

    @property
    def ForwardRBFInstance(self):
        if self._ForwardRBFInstance is None:
            self._ForwardRBFInstance = RBFWithLinearCorrection(self.SourcePoints, self.TargetPoints)

        return self._ForwardRBFInstance

    def InitializeDataStructures(self):

        if self.NumControlPoints <= NumberOfControlPointsToTriggerMultiprocessing:
            Pool = nornir_pools.GetGlobalThreadPool()
        else:
            Pool = nornir_pools.GetGlobalMultithreadingPool()

        ForwardTask = Pool.add_task("Solve forward RBF transform", RBFWithLinearCorrection, self.SourcePoints, self.TargetPoints)
        ReverseTask = Pool.add_task("Solve reverse RBF transform", RBFWithLinearCorrection, self.TargetPoints, self.SourcePoints)

        super(MeshWithRBFFallback, self).InitializeDataStructures()

        self._ForwardRBFInstance = ForwardTask.wait_return()
        self._ReverseRBFInstance = ReverseTask.wait_return()


    def ClearDataStructures(self):
        '''Something about the transform has changed, for example the points. 
           Clear out our data structures so we do not use bad data'''

        super(MeshWithRBFFallback, self).ClearDataStructures()

        self._ForwardRBFInstance = None
        self._ReverseRBFInstance = None

    def OnFixedPointChanged(self):
        super(MeshWithRBFFallback, self).OnFixedPointChanged()
        self._ForwardRBFInstance = None
        self._ReverseRBFInstance = None


    def OnWarpedPointChanged(self):
        super(MeshWithRBFFallback, self).OnWarpedPointChanged()
        self._ForwardRBFInstance = None
        self._ReverseRBFInstance = None

    def Transform(self, points, **kwargs):
        '''
        Transform from warped space to fixed space
        
        :param ndarray points: [[ControlY, ControlX, MappedY, MappedX],...] 
        :param bool extrapolate: Set to false if points falling outside the convex hull of control points should be removed from the return values
        '''

        points = nornir_imageregistration.EnsurePointsAre2DNumpyArray(points)

        if points.shape[0] == 0:
            return [];

        TransformedPoints = super(MeshWithRBFFallback, self).Transform(points)
        extrapolate = kwargs.get('extrapolate', True)
        if not extrapolate:
            return TransformedPoints

        (GoodPoints, InvalidIndicies) = utils.InvalidIndicies(TransformedPoints)

        if(len(InvalidIndicies) == 0):
            return TransformedPoints;
        else:
            if len(points) > 1:
                # print InvalidIndicies;
                BadPoints = points[InvalidIndicies];
            else:
                BadPoints = points;

        BadPoints = numpy.asarray(BadPoints, dtype=numpy.float32);
        if not (BadPoints.dtype == numpy.float32 or BadPoints.dtype == numpy.float64):
            BadPoints = numpy.asarray(BadPoints, dtype=numpy.float32)
            
        FixedPoints = self.ForwardRBFInstance.Transform(BadPoints);

        TransformedPoints[InvalidIndicies] = FixedPoints;
        return TransformedPoints;

    def InverseTransform(self, points, **kwargs):
        '''
        Transform from fixed space to warped space
        
        :param bool extrapolate: Set to false if points falling outside the convex hull of control points should be removed from the return values
        ''' 

        points = nornir_imageregistration.EnsurePointsAre2DNumpyArray(points)

        if points.shape[0] == 0:
            return [];

        TransformedPoints = super(MeshWithRBFFallback, self).InverseTransform(points)
        extrapolate = kwargs.get('extrapolate', True)
        if not extrapolate:
            return TransformedPoints

        (GoodPoints, InvalidIndicies) = utils.InvalidIndicies(TransformedPoints)
 
        if(len(InvalidIndicies) == 0):
            return TransformedPoints
        else:
            if points.ndim > 1:
                BadPoints = points[InvalidIndicies]
            else:
                BadPoints = points  # This is likely no longer needed since this function always returns a 2D array now

        if not (BadPoints.dtype == numpy.float32 or BadPoints.dtype == numpy.float64):
            BadPoints = numpy.asarray(BadPoints, dtype=numpy.float32)

        FixedPoints = self.ReverseRBFInstance.Transform(BadPoints)

        TransformedPoints[InvalidIndicies] = FixedPoints
        return TransformedPoints

    def __init__(self, pointpairs):
        ''' 
        :param ndarray pointpairs: [ControlY, ControlX, MappedY, MappedX] 
        '''
        super(MeshWithRBFFallback, self).__init__(pointpairs)

        self._ReverseRBFInstance = None
        self._ForwardRBFInstance = None
        
    @staticmethod
    def Load(TransformString, pixelSpacing=None):
        return nornir_imageregistration.transforms.factory.ParseMeshTransform(TransformString, pixelSpacing)


if __name__ == '__main__':
    p = numpy.array([[0, 0, 0, 0],
                  [0, 10, 0, -10],
                  [10, 0, -10, 0],
                  [10, 10, -10, -10]])

    (Fixed, Moving) = numpy.hsplit(p, 2);
    T = RBFWithLinearCorrection(Fixed, Moving);

    warpedPoints = [[0, 0], [-5, -5]];
    fp = T.ViewTransform(warpedPoints);
    print(("__Transform " + str(warpedPoints) + " to " + str(fp)))
    wp = T.InverseTransform(fp);


    print("Fixed Verts")
    print(T.FixedTriangles);
    print("\nWarped Verts")
    print(T.WarpedTriangles);

    T.AddPoint([5, 5, -5, -5]);
    print("\nPoint added")
    print("Fixed Verts")
    print(T.FixedTriangles);
    print("\nWarped Verts")
    print(T.WarpedTriangles);

    T.AddPoint([5, 5, 5, 5]);
    print("\nDuplicate Point added")
    print("Fixed Verts")
    print(T.FixedTriangles);
    print("\nWarped Verts")
    print(T.WarpedTriangles);

    warpedPoint = [[-5, -5]];
    fp = T.ViewTransform(warpedPoint);
    print(("__Transform " + str(warpedPoint) + " to " + str(fp)))
    wp = T.InverseTransform(fp);

    T.UpdatePoint(3, [10, 15, -10, -15]);
    print("\nPoint updated")
    print("Fixed Verts")
    print(T.FixedTriangles);
    print("\nWarped Verts")
    print(T.WarpedTriangles);

    warpedPoint = [[-9, -14]];
    fp = T.ViewTransform(warpedPoint);
    print(("__Transform " + str(warpedPoint) + " to " + str(fp)))
    wp = T.InverseTransform(fp);

    T.RemovePoint(1);
    print("\nPoint removed")
    print("Fixed Verts")
    print(T.FixedTriangles);
    print("\nWarped Verts")
    print(T.WarpedTriangles);




    print("\nFixedPointsInRect")
    print(T.GetFixedPointsRect([-1, -1, 14, 4]));


