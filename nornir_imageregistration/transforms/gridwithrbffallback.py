"""
Created on Oct 18, 2012

@author: Jamesan
"""

import numpy as np
try:
    import cupy as cp
    from cupyx.scipy.interpolate import RegularGridInterpolator as cuRegularGridInterpolator

    #import cupyx
    #from cupyx.scipy.interpolate import RegularGridInterpolator as cuRegularGridInterpolator
    #from cupyx.scipy.interpolate import RBFInterpolator as cuRBFInterpolator
except ModuleNotFoundError:
    import cupy_thunk as cp
    #import cupyx_thunk as cupyx
except ImportError:
    import cupy_thunk as cp
    #import cupyx_thunk as cupyx
import scipy.spatial
from scipy.interpolate import RegularGridInterpolator as RegularGridInterpolator
from numpy.typing import NDArray

import nornir_imageregistration
import nornir_imageregistration.transforms
from nornir_imageregistration.transforms import float_to_shortest_string
from nornir_imageregistration.grid_subdivision import ITKGridDivision
from nornir_imageregistration.transforms.base import IDiscreteTransform, ITransformScaling, \
    ITransformRelativeScaling, ITransformTargetRotation, ITargetSpaceControlPointEdit, IControlPoints, IGridTransform, \
    ITriangulatedTargetSpace
from nornir_imageregistration.transforms.defaulttransformchangeevents import DefaultTransformChangeEvents
from nornir_imageregistration.transforms.transform_type import TransformType
from nornir_imageregistration.transforms.landmark import Landmark_GPU, Landmark_CPU
from . import utils


class GridWithRBFFallback(IDiscreteTransform, IControlPoints, ITransformScaling, ITransformRelativeScaling,
                          ITransformTargetRotation,
                          ITargetSpaceControlPointEdit, IGridTransform, ITriangulatedTargetSpace,
                          DefaultTransformChangeEvents):
    """
    classdocs
    """

    @property
    def type(self) -> TransformType:
        return self._discrete_transform.type

    @property
    def grid(self) -> ITKGridDivision:
        return self._discrete_transform.grid

    @property
    def grid_dims(self) -> tuple[int, int]:
        return self._grid._grid_dims

    def ToITKString(self) -> str:
        return self._discrete_transform.ToITKString()

    def __getstate__(self):
        odict = super(GridWithRBFFallback, self).__getstate__()
        odict['_discrete_transform'] = self._discrete_transform
        odict['_continuous_transform'] = self._continuous_transform
        return odict

    def __setstate__(self, dictionary):
        super(GridWithRBFFallback, self).__setstate__(dictionary)
        self._discrete_transform = dictionary['_discrete_transform']
        self._continuous_transform = dictionary['_continuous_transform']

    def InitializeDataStructures(self):
        self._continuous_transform.InitializeDataStructures()
        # self._discrete_transform.InitializeDataStructures() Grid does not have an Initialize data structures call

    def ClearDataStructures(self):
        """Something about the transform has changed, for example the points.
           Clear out our data structures so we do not use bad data"""
        self._continuous_transform.ClearDataStructures()
        self._discrete_transform.ClearDataStructures()

    def OnFixedPointChanged(self):
        self._continuous_transform.OnFixedPointChanged()
        self._discrete_transform.OnFixedPointChanged()
        self.OnTransformChanged()

    def OnWarpedPointChanged(self):
        self._continuous_transform.OnWarpedPointChanged()
        self._discrete_transform.OnWarpedPointChanged()
        self.OnTransformChanged()

    def Transform(self, points: NDArray[np.floating], **kwargs) -> NDArray[np.floating]:
        """
        Transform from warped space to fixed space
        :param ndarray points: [[ControlY, ControlX, MappedY, MappedX],...]
        """

        points = nornir_imageregistration.EnsurePointsAre2DNumpyArray(points)

        if points.shape[0] == 0:
            return np.empty((0, 2), dtype=points.dtype)

        TransformedPoints = self._discrete_transform.Transform(points)
        extrapolate = kwargs.get('extrapolate', True)
        if not extrapolate:
            return TransformedPoints

        (GoodPoints, InvalidIndicies, ValidIndicies) = utils.InvalidIndicies(TransformedPoints)

        if len(InvalidIndicies) == 0:
            return TransformedPoints
        else:
            if len(points) > 1:
                # print InvalidIndicies;
                BadPoints = points[InvalidIndicies]
            else:
                BadPoints = points

        BadPoints = np.asarray(BadPoints, dtype=np.float32)
        if not (BadPoints.dtype == np.float32 or BadPoints.dtype == np.float64):
            BadPoints = np.asarray(BadPoints, dtype=np.float32)

        FixedPoints = self._continuous_transform.Transform(BadPoints)

        TransformedPoints[InvalidIndicies] = FixedPoints
        return TransformedPoints

    def InverseTransform(self, points: NDArray[np.floating], **kwargs):
        """
        Transform from fixed space to warped space
        :param points:
        """

        points = nornir_imageregistration.EnsurePointsAre2DNumpyArray(points)

        if points.shape[0] == 0:
            return np.empty((0, 2), dtype=points.dtype)

        TransformedPoints = self._discrete_transform.InverseTransform(points)
        extrapolate = kwargs.get('extrapolate', True)
        if not extrapolate:
            return TransformedPoints

        (GoodPoints, InvalidIndicies, ValidIndicies) = utils.InvalidIndicies(TransformedPoints)

        if len(InvalidIndicies) == 0:
            return TransformedPoints
        else:
            if points.ndim > 1:
                BadPoints = points[InvalidIndicies]
            else:
                BadPoints = points  # This is likely no longer needed since this function always returns a 2D array now

        if not (BadPoints.dtype == np.float32 or BadPoints.dtype == np.float64):
            BadPoints = np.asarray(BadPoints, dtype=np.float32)

        FixedPoints = self._continuous_transform.InverseTransform(BadPoints)

        TransformedPoints[InvalidIndicies] = FixedPoints
        return TransformedPoints

    def __init__(self,
                 grid: ITKGridDivision):
        """
        :param ndarray pointpairs: [ControlY, ControlX, MappedY, MappedX]
        """
        super(GridWithRBFFallback, self).__init__()

        self._discrete_transform = nornir_imageregistration.transforms.GridTransform(grid)
        self._continuous_transform = nornir_imageregistration.transforms.TwoWayRBFWithLinearCorrection(
            grid.SourcePoints, grid.TargetPoints)

    def AddTransform(self, mappedTransform: IControlPoints, EnrichTolerance=None, create_copy=True):
        '''Take the control points of the mapped transform and map them through our transform so the control points are in our controlpoint space'''
        return nornir_imageregistration.transforms.AddTransforms(self, mappedTransform, EnrichTolerance=EnrichTolerance,
                                                                 create_copy=create_copy)

    @staticmethod
    def Load(TransformString: str, pixelSpacing=None):
        return nornir_imageregistration.transforms.factory.ParseGridTransform(TransformString, pixelSpacing)

    @property
    def MappedBoundingBox(self) -> nornir_imageregistration.Rectangle:
        """Bounding box of mapped space points"""
        return self._discrete_transform.MappedBoundingBox

    @property
    def FixedBoundingBox(self) -> nornir_imageregistration.Rectangle:
        return self._discrete_transform.FixedBoundingBox

    @property
    def SourcePoints(self) -> NDArray[np.floating]:
        return self._discrete_transform.SourcePoints

    @property
    def TargetPoints(self) -> NDArray[np.floating]:
        return self._discrete_transform.TargetPoints

    @property
    def points(self) -> NDArray[np.floating]:
        return self._discrete_transform.points

    @property
    def NumControlPoints(self) -> int:
        return self._discrete_transform.NumControlPoints

    def NearestTargetPoint(self, points: NDArray[np.floating]) -> tuple((float | NDArray[np.floating], int | NDArray[np.integer])):
        '''
        Return the fixed points nearest to the query points
        :return: Distance, Index
        '''
        return self._discrete_transform.NearestTargetPoint(points)

    def NearestFixedPoint(self, points: NDArray[np.floating]) -> tuple((float | NDArray[np.floating], int | NDArray[np.integer])):
        '''
        Return the fixed points nearest to the query points
        :return: Distance, Index
        '''
        return self._discrete_transform.NearestFixedPoint(points)

    def NearestSourcePoint(self, points: NDArray[np.floating]) -> tuple((float | NDArray[np.floating], int | NDArray[np.integer])):
        '''
        Return the warped points nearest to the query points
        :return: Distance, Index
        '''
        return self._discrete_transform.NearestSourcePoint(points)

    def NearestWarpedPoint(self, points: NDArray[np.floating]) -> tuple((float | NDArray[np.floating], int | NDArray[np.integer])):
        '''
        Return the warped points nearest to the query points
        :return: Distance, Index
        '''
        return self._discrete_transform.NearestWarpedPoint(points)

    def GetFixedPointsInRect(self, bounds: nornir_imageregistration.Rectangle | NDArray[np.floating]):
        '''bounds = [bottom left top right]'''
        return self._discrete_transform.GetPointPairsInRect(self.TargetPoints, bounds)

    def GetWarpedPointsInRect(self, bounds: nornir_imageregistration.Rectangle | NDArray[np.floating]):
        '''bounds = [bottom left top right]'''
        return self._discrete_transform.GetPointPairsInRect(self.SourcePoints, bounds)

    def GetPointInFixedRect(self, bounds: nornir_imageregistration.Rectangle | NDArray[np.floating]):
        '''bounds = [bottom left top right]'''
        return self._discrete_transform.GetPointPairsInRect(self.TargetPoints, bounds)

    def GetPointsInWarpedRect(self, bounds: nornir_imageregistration.Rectangle | NDArray[np.floating]):
        '''bounds = [bottom left top right]'''
        return self._discrete_transform.GetPointPairsInRect(self.SourcePoints, bounds)

    def GetPointPairsInTargetRect(self, bounds: nornir_imageregistration.Rectangle):
        '''Return the point pairs inside the rectangle defined in target space'''
        return self._discrete_transform.GetPointPairsInTargetRect(bounds)

    def GetPointPairsInSourceRect(self, bounds: nornir_imageregistration.Rectangle):
        '''Return the point pairs inside the rectangle defined in source space'''
        return self._discrete_transform.GetPointPairsInSourceRect(bounds)

    def PointPairsToWarpedPoints(self, points: NDArray[np.floating]):
        '''Return the warped points from a set of target-source point pairs'''
        return self._discrete_transform.PointPairsToWarpedPoints(points)

    def PointPairsToTargetPoints(self, points: NDArray[np.floating]):
        '''Return the target points from a set of target-source point pairs'''
        return self._discrete_transform.PointPairsToTargetPoints(points)

    @property
    def fixedtri(self) -> scipy.spatial.Delaunay:
        return self._discrete_transform.FixedTriangles

    @property
    def FixedTriangles(self) -> scipy.spatial.Delaunay:
        return self._discrete_transform.FixedTriangles

    @property
    def target_space_trianglulation(self) -> scipy.spatial.Delaunay:
        return self._discrete_transform.target_space_trianglulation

    def TranslateFixed(self, offset: NDArray[np.floating]):
        '''Translate all fixed points by the specified amount'''

        self._discrete_transform.TranslateFixed(offset)
        self._continuous_transform.TranslateFixed(offset)
        self.OnFixedPointChanged()

    def TranslateWarped(self, offset: NDArray[np.floating]):
        '''Translate all warped points by the specified amount'''
        self._discrete_transform.TranslateWarped(offset)
        self._continuous_transform.TranslateWarped(offset)
        self.OnWarpedPointChanged()

    def Scale(self, scalar: float):
        '''Scale both warped and control space by scalar'''
        self._discrete_transform.Scale(scalar)
        self._continuous_transform.Scale(scalar)
        self.OnTransformChanged()

    def ScaleWarped(self, scalar: float):
        '''Scale source space control points by scalar'''
        self._discrete_transform.ScaleWarped(scalar)
        self._continuous_transform.ScaleWarped(scalar)
        self.OnTransformChanged()

    def ScaleFixed(self, scalar: float):
        '''Scale target space control points by scalar'''
        self._discrete_transform.ScaleFixed(scalar)
        self._continuous_transform.ScaleFixed(scalar)
        self.OnTransformChanged()

    def RotateTargetPoints(self, rangle: float, rotation_center: NDArray[np.floating] | None):
        '''Rotate all warped points about a center by a given angle'''
        if rotation_center is None:
            rotation_center = self.FixedBoundingBox.Center

        self._discrete_transform.RotateTargetPoints(rangle, rotation_center)
        self._continuous_transform = nornir_imageregistration.transforms.TwoWayRBFWithLinearCorrection(
            self._discrete_transform.SourcePoints, self._discrete_transform.TargetPoints)

        self.OnTransformChanged()

    def UpdateTargetPointsByIndex(self, index: int | NDArray[np.integer], point: NDArray[np.floating] | None) -> int | NDArray[np.integer]:
        # Using this may cause errors since the discrete and continuous transforms are not guaranteed to use the same index
        result = self._discrete_transform.UpdateTargetPointsByIndex(index, point)
        self._continuous_transform.UpdateTargetPointsByIndex(index, point)
        self.OnTransformChanged()
        return result

    def UpdateTargetPointsByPosition(self, index: NDArray[np.floating], point: NDArray[np.floating] | None) -> int | NDArray[np.integer]:
        result = self._discrete_transform.UpdateTargetPointsByPosition(index, point)
        self._continuous_transform.UpdateTargetPointsByPosition(index, point)
        self.OnTransformChanged()
        return result


class GridWithRBFFallback_GPUComponent(IDiscreteTransform, IControlPoints, ITransformScaling,
                              ITransformRelativeScaling, ITransformTargetRotation,
                              ITargetSpaceControlPointEdit, IGridTransform, ITriangulatedTargetSpace,
                              DefaultTransformChangeEvents):
    """
    classdocs
    """

    @property
    def type(self) -> TransformType:
        return self._discrete_transform.type

    @property
    def grid(self) -> ITKGridDivision:
        return self._discrete_transform.grid

    @property
    def grid_dims(self) -> tuple[int, int]:
        return self._grid._grid_dims

    def ToITKString(self) -> str:
        return self._discrete_transform.ToITKString()

    def __getstate__(self):
        odict = super(GridWithRBFFallback_GPUComponent, self).__getstate__()
        odict['_discrete_transform'] = self._discrete_transform
        odict['_continuous_transform'] = self._continuous_transform
        return odict

    def __setstate__(self, dictionary):
        super(GridWithRBFFallback_GPUComponent, self).__setstate__(dictionary)
        self._discrete_transform = dictionary['_discrete_transform']
        self._continuous_transform = dictionary['_continuous_transform']

    def InitializeDataStructures(self):
        self._continuous_transform.InitializeDataStructures()
        # self._discrete_transform.InitializeDataStructures() Grid does not have an Initialize data structures call

    def ClearDataStructures(self):
        """Something about the transform has changed, for example the points.
           Clear out our data structures so we do not use bad data"""
        self._continuous_transform.ClearDataStructures()
        self._discrete_transform.ClearDataStructures()

    def OnFixedPointChanged(self):
        self._continuous_transform.OnFixedPointChanged()
        self._discrete_transform.OnFixedPointChanged()
        self.OnTransformChanged()

    def OnWarpedPointChanged(self):
        self._continuous_transform.OnWarpedPointChanged()
        self._discrete_transform.OnWarpedPointChanged()
        self.OnTransformChanged()

    def Transform(self, points: NDArray[np.floating], **kwargs) -> NDArray[np.floating]:
        """
        Transform from warped space to fixed space
        :param ndarray points: [[ControlY, ControlX, MappedY, MappedX],...]
        """

        points = nornir_imageregistration.EnsurePointsAre2DCuPyArray(points)

        if points.shape[0] == 0:
            return cp.empty((0, 2), dtype=points.dtype)

        TransformedPoints = self._discrete_transform.Transform(points)
        extrapolate = kwargs.get('extrapolate', True)
        if not extrapolate:
            return TransformedPoints

        (GoodPoints, InvalidIndicies, ValidIndicies) = utils.InvalidIndicies(TransformedPoints)

        if len(InvalidIndicies) == 0:
            return TransformedPoints
        else:
            if len(points) > 1:
                # print InvalidIndicies;
                BadPoints = points[InvalidIndicies]
            else:
                BadPoints = points

        # BadPoints = cp.asarray(BadPoints, dtype=np.float32)
        if not (BadPoints.dtype == np.float32 or BadPoints.dtype == np.float64):
            BadPoints = cp.asarray(BadPoints, dtype=np.float32)

        FixedPoints = self._continuous_transform.Transform(BadPoints)

        TransformedPoints[InvalidIndicies] = FixedPoints

        # Because of a missing CuPy LinearNDInterpolator method we sometimes have to fallback to np, so ensure we hand back points on the GPU
        TransformedPoints = nornir_imageregistration.EnsurePointsAre2DCuPyArray(TransformedPoints)
        return TransformedPoints

    def InverseTransform(self, points: NDArray[np.floating], **kwargs):
        """
        Transform from fixed space to warped space
        :param points:
        """

        points = nornir_imageregistration.EnsurePointsAre2DCuPyArray(points)

        if points.shape[0] == 0:
            return cp.empty((0, 2), dtype=points.dtype)

        TransformedPoints = self._discrete_transform.InverseTransform(points)
        extrapolate = kwargs.get('extrapolate', True)
        if not extrapolate:
            return TransformedPoints

        (GoodPoints, InvalidIndicies, ValidIndicies) = utils.InvalidIndicies(TransformedPoints)

        if len(InvalidIndicies) == 0:
            return TransformedPoints
        else:
            if points.ndim > 1:
                BadPoints = points[InvalidIndicies]
            else:
                BadPoints = points  # This is likely no longer needed since this function always returns a 2D array now

        if not (BadPoints.dtype == np.float32 or BadPoints.dtype == np.float64):
            BadPoints = cp.asarray(BadPoints, dtype=np.float32)

        FixedPoints = self._continuous_transform.InverseTransform(BadPoints)
        TransformedPoints[InvalidIndicies] = FixedPoints

        #Because of a missing CuPy LinearNDInterpolator method we sometimes have to fallback to np, so ensure we hand back points on the GPU
        TransformedPoints = nornir_imageregistration.EnsurePointsAre2DCuPyArray(TransformedPoints)
        return TransformedPoints


    def __init__(self,
                 grid: ITKGridDivision):
        """
        :param ndarray pointpairs: [ControlY, ControlX, MappedY, MappedX]
        """
        super(GridWithRBFFallback_GPUComponent, self).__init__()

        # self._discrete_transform = nornir_imageregistration.transforms.GridTransform(grid)
        self._discrete_transform = nornir_imageregistration.transforms.GridTransform_GPUComponent(grid)
        self._continuous_transform = nornir_imageregistration.transforms.TwoWayRBFWithLinearCorrection_GPUComponent(
            grid.SourcePoints, grid.TargetPoints)

    def AddTransform(self, mappedTransform: IControlPoints, EnrichTolerance=None, create_copy=True):
        '''Take the control points of the mapped transform and map them through our transform so the control points are in our controlpoint space'''
        return nornir_imageregistration.transforms.AddTransforms(self, mappedTransform, EnrichTolerance=EnrichTolerance,
                                                                 create_copy=create_copy)

    @staticmethod
    def Load(TransformString: str, pixelSpacing=None):
        return nornir_imageregistration.transforms.factory.ParseGridTransform(TransformString, pixelSpacing)

    @property
    def MappedBoundingBox(self) -> nornir_imageregistration.Rectangle:
        """Bounding box of mapped space points"""
        return self._discrete_transform.MappedBoundingBox

    @property
    def FixedBoundingBox(self) -> nornir_imageregistration.Rectangle:
        return self._discrete_transform.FixedBoundingBox

    @property
    def SourcePoints(self) -> NDArray[np.floating]:
        return self._discrete_transform.SourcePoints

    @property
    def TargetPoints(self) -> NDArray[np.floating]:
        return self._discrete_transform.TargetPoints

    @property
    def points(self) -> NDArray[np.floating]:
        return self._discrete_transform.points

    @property
    def NumControlPoints(self) -> int:
        return self._discrete_transform.NumControlPoints

    def NearestTargetPoint(self, points: NDArray[np.floating]) -> tuple((float | NDArray[np.floating], int | NDArray[np.integer])):
        '''
        Return the fixed points nearest to the query points
        :return: Distance, Index
        '''
        return self._discrete_transform.NearestTargetPoint(points)

    def NearestFixedPoint(self, points: NDArray[np.floating]) -> tuple((float | NDArray[np.floating], int | NDArray[np.integer])):
        '''
        Return the fixed points nearest to the query points
        :return: Distance, Index
        '''
        return self._discrete_transform.NearestFixedPoint(points)

    def NearestSourcePoint(self, points: NDArray[np.floating]) -> tuple((float | NDArray[np.floating], int | NDArray[np.integer])):
        '''
        Return the warped points nearest to the query points
        :return: Distance, Index
        '''
        return self._discrete_transform.NearestSourcePoint(points)

    def NearestWarpedPoint(self, points: NDArray[np.floating]) -> tuple((float | NDArray[np.floating], int | NDArray[np.integer])):
        '''
        Return the warped points nearest to the query points
        :return: Distance, Index
        '''
        return self._discrete_transform.NearestWarpedPoint(points)

    def GetFixedPointsInRect(self, bounds: nornir_imageregistration.Rectangle | NDArray[np.floating]):
        '''bounds = [bottom left top right]'''
        return self._discrete_transform.GetPointPairsInRect(self.TargetPoints, bounds)

    def GetWarpedPointsInRect(self, bounds: nornir_imageregistration.Rectangle | NDArray[np.floating]):
        '''bounds = [bottom left top right]'''
        return self._discrete_transform.GetPointPairsInRect(self.SourcePoints, bounds)

    def GetPointInFixedRect(self, bounds: nornir_imageregistration.Rectangle | NDArray[np.floating]):
        '''bounds = [bottom left top right]'''
        return self._discrete_transform.GetPointPairsInRect(self.TargetPoints, bounds)

    def GetPointsInWarpedRect(self, bounds: nornir_imageregistration.Rectangle | NDArray[np.floating]):
        '''bounds = [bottom left top right]'''
        return self._discrete_transform.GetPointPairsInRect(self.SourcePoints, bounds)

    def GetPointPairsInTargetRect(self, bounds: nornir_imageregistration.Rectangle):
        '''Return the point pairs inside the rectangle defined in target space'''
        return self._discrete_transform.GetPointPairsInTargetRect(bounds)

    def GetPointPairsInSourceRect(self, bounds: nornir_imageregistration.Rectangle):
        '''Return the point pairs inside the rectangle defined in source space'''
        return self._discrete_transform.GetPointPairsInSourceRect(bounds)

    def PointPairsToWarpedPoints(self, points: NDArray[np.floating]):
        '''Return the warped points from a set of target-source point pairs'''
        return self._discrete_transform.PointPairsToWarpedPoints(points)

    def PointPairsToTargetPoints(self, points: NDArray[np.floating]):
        '''Return the target points from a set of target-source point pairs'''
        return self._discrete_transform.PointPairsToTargetPoints(points)

    @property
    def fixedtri(self) -> scipy.spatial.Delaunay:
        return self._discrete_transform.FixedTriangles

    @property
    def FixedTriangles(self) -> scipy.spatial.Delaunay:
        return self._discrete_transform.FixedTriangles

    @property
    def target_space_trianglulation(self) -> scipy.spatial.Delaunay:
        return self._discrete_transform.target_space_trianglulation

    def TranslateFixed(self, offset: NDArray[np.floating]):
        '''Translate all fixed points by the specified amount'''

        self._discrete_transform.TranslateFixed(offset)
        self._continuous_transform.TranslateFixed(offset)
        self.OnFixedPointChanged()

    def TranslateWarped(self, offset: NDArray[np.floating]):
        '''Translate all warped points by the specified amount'''
        self._discrete_transform.TranslateWarped(offset)
        self._continuous_transform.TranslateWarped(offset)
        self.OnWarpedPointChanged()

    def Scale(self, scalar: float):
        '''Scale both warped and control space by scalar'''
        self._discrete_transform.Scale(scalar)
        self._continuous_transform.Scale(scalar)
        self.OnTransformChanged()

    def ScaleWarped(self, scalar: float):
        '''Scale source space control points by scalar'''
        self._discrete_transform.ScaleWarped(scalar)
        self._continuous_transform.ScaleWarped(scalar)
        self.OnTransformChanged()

    def ScaleFixed(self, scalar: float):
        '''Scale target space control points by scalar'''
        self._discrete_transform.ScaleFixed(scalar)
        self._continuous_transform.ScaleFixed(scalar)
        self.OnTransformChanged()

    def RotateTargetPoints(self, rangle: float, rotation_center: NDArray[np.floating] | None):
        '''Rotate all warped points about a center by a given angle'''
        if rotation_center is None:
            rotation_center = self.FixedBoundingBox.Center

        self._discrete_transform.RotateTargetPoints(rangle, rotation_center)
        self._continuous_transform = nornir_imageregistration.transforms.TwoWayRBFWithLinearCorrection(
            self._discrete_transform.SourcePoints, self._discrete_transform.TargetPoints)

        self.OnTransformChanged()

    def UpdateTargetPointsByIndex(self, index: int | NDArray[np.integer], point: NDArray[np.floating] | None) -> int | NDArray[np.integer]:
        # Using this may cause errors since the discrete and continuous transforms are not guaranteed to use the same index
        result = self._discrete_transform.UpdateTargetPointsByIndex(index, point)
        self._continuous_transform.UpdateTargetPointsByIndex(index, point)
        self.OnTransformChanged()
        return result

    def UpdateTargetPointsByPosition(self, index: NDArray[np.floating], point: NDArray[np.floating] | None) -> int | NDArray[np.integer]:
        result = self._discrete_transform.UpdateTargetPointsByPosition(index, point)
        self._continuous_transform.UpdateTargetPointsByPosition(index, point)
        self.OnTransformChanged()
        return result


class GridWithRBFInterpolator_Direct_GPU(Landmark_GPU):
    """
    classdocs
    """

    @property
    def type(self) -> TransformType:
        return TransformType.GRID

    @property
    def grid(self) -> ITKGridDivision:
        return self._grid

    @property
    def grid_dims(self) -> tuple[int, int]:
        return self._grid._grid_dims

    def ToITKString(self) -> str:
        numPoints = self.SourcePoints.shape[0]
        (bottom, left, top, right) = self.MappedBoundingBox.ToTuple()
        image_width = (
                right - left)  # We remove one because a 10x10 image is mappped from 0,0 to 10,10, which means the bounding box will be Left=0, Right=10, and width is 11 unless we correct for it.
        image_height = (top - bottom)

        YDim = int(self._grid._grid_dims[0]) - 1  # For whatever reason ITK subtracts one from the dimensions
        XDim = int(self._grid._grid_dims[1]) - 1  # For whatever reason ITK subtracts one from the dimensions

        output = ["GridTransform_double_2_2 vp " + str(numPoints * 2)]
        template = " %(cx)s %(cy)s"
        NumAdded = int(0)
        for CY, CX, MY, MX in self.points:
            pstr = template % {'cx': float_to_shortest_string(CX, 3), 'cy': float_to_shortest_string(CY, 3)}
            output.append(pstr)
            NumAdded = NumAdded + 1

        # ITK expects the image dimensions to be the actual dimensions of the image.  So if an image is 1024 pixels wide
        # then 1024 should be written to the file.
        output.append(f" fp 7 0 {YDim:d} {XDim:d} {left:g} {bottom:g} {image_width:g} {image_height:g}")
        transform_string = ''.join(output)

        return transform_string

    def __getstate__(self):

        odict = super(GridWithRBFInterpolator_Direct_GPU, self).__getstate__()
        odict['_ReverseRBFInstance'] = self._ReverseRBFInstance
        odict['_ForwardRBFInstance'] = self._ForwardRBFInstance
        return odict

    def __setstate__(self, dictionary):
        super(GridWithRBFInterpolator_Direct_GPU, self).__setstate__(dictionary)

    @property
    def ReverseRBFInstance(self):
        if self._ReverseRBFInstance is None:
            self._ReverseRBFInstance = super(GridWithRBFInterpolator_Direct_GPU, self).InverseInterpolator()

        return self._ReverseRBFInstance

    @property
    def ForwardRBFInstance(self):
        if self._ForwardRBFInstance is None:
            self._ForwardRBFInstance = super(GridWithRBFInterpolator_Direct_GPU, self).ForwardInterpolator()

        return self._ForwardRBFInstance

    # def InitializeDataStructures(self):
    #
    #     self._ForwardRBFInstance = cuRBFInterpolator(self.SourcePoints, self.TargetPoints)
    #     self._ReverseRBFInstance = cuRBFInterpolator(self.TargetPoints, self.SourcePoints)
    #
    #
    # def ClearDataStructures(self):
    #     """Something about the transform has changed, for example the points.
    #        Clear out our data structures so we do not use bad data"""
    #
    #     super(GridWithRBFInterpolator_Direct_GPU, self).ClearDataStructures()
    #
    #     self._ForwardRBFInstance = None
    #     self._ReverseRBFInstance = None

    def OnFixedPointChanged(self):
        super(GridWithRBFInterpolator_Direct_GPU, self).OnFixedPointChanged()
        self._ForwardRBFInstance = None
        self._ReverseRBFInstance = None

    def OnWarpedPointChanged(self):
        super(GridWithRBFInterpolator_Direct_GPU, self).OnWarpedPointChanged()
        self._ForwardRBFInstance = None
        self._ReverseRBFInstance = None

    def Transform(self, points, **kwargs):
        """
        Transform from warped space to fixed space
        :param ndarray points: [[ControlY, ControlX, MappedY, MappedX],...]
        """
        print("GridWithRBFInterpolator_Direct_GPU -> TRANSFORM()")
        points = nornir_imageregistration.EnsurePointsAre2DCuPyArray(points)

        TransformedPoints = super(GridWithRBFInterpolator_Direct_GPU, self).Transform(points)
        return TransformedPoints

    def InverseTransform(self, points, **kwargs):
        """
        Transform from fixed space to warped space
        :param points:
        """
        print("GridWithRBFInterpolator_Direct_GPU -> INVERSETRANSFORM()")

        points = nornir_imageregistration.EnsurePointsAre2DCuPyArray(points)

        iTransformedPoints = super(GridWithRBFInterpolator_Direct_GPU, self).InverseTransform(points)
        return iTransformedPoints

    def __init__(self, grid: ITKGridDivision):
        """
        :param ndarray pointpairs: [ControlY, ControlX, MappedY, MappedX]
        """
        self._grid = grid
        try:
            control_points = cp.hstack((grid.TargetPoints, grid.SourcePoints))
        except:
            print(f'Invalid grid: {grid.TargetPoints} {grid.SourcePoints}')
            raise

        super(GridWithRBFInterpolator_Direct_GPU, self).__init__(control_points)

        self._ReverseRBFInstance = None
        self._ForwardRBFInstance = None

    @staticmethod
    def Load(TransformString: str, pixelSpacing=None):
        return nornir_imageregistration.transforms.factory.ParseGridTransform(TransformString, pixelSpacing)

class GridWithRBFInterpolator_Direct_CPU(Landmark_CPU):
    """
    classdocs
    """

    @property
    def type(self) -> TransformType:
        return TransformType.GRID

    @property
    def grid(self) -> ITKGridDivision:
        return self._grid

    @property
    def grid_dims(self) -> tuple[int, int]:
        return self._grid._grid_dims

    def ToITKString(self) -> str:
        numPoints = self.SourcePoints.shape[0]
        (bottom, left, top, right) = self.MappedBoundingBox.ToTuple()
        image_width = (
                right - left)  # We remove one because a 10x10 image is mappped from 0,0 to 10,10, which means the bounding box will be Left=0, Right=10, and width is 11 unless we correct for it.
        image_height = (top - bottom)

        YDim = int(self._grid._grid_dims[0]) - 1  # For whatever reason ITK subtracts one from the dimensions
        XDim = int(self._grid._grid_dims[1]) - 1  # For whatever reason ITK subtracts one from the dimensions

        output = ["GridTransform_double_2_2 vp " + str(numPoints * 2)]
        template = " %(cx)s %(cy)s"
        NumAdded = int(0)
        for CY, CX, MY, MX in self.points:
            pstr = template % {'cx': float_to_shortest_string(CX, 3), 'cy': float_to_shortest_string(CY, 3)}
            output.append(pstr)
            NumAdded = NumAdded + 1

        # ITK expects the image dimensions to be the actual dimensions of the image.  So if an image is 1024 pixels wide
        # then 1024 should be written to the file.
        output.append(f" fp 7 0 {YDim:d} {XDim:d} {left:g} {bottom:g} {image_width:g} {image_height:g}")
        transform_string = ''.join(output)

        return transform_string

    def __getstate__(self):

        odict = super(GridWithRBFInterpolator_Direct_CPU, self).__getstate__()
        odict['_ReverseRBFInstance'] = self._ReverseRBFInstance
        odict['_ForwardRBFInstance'] = self._ForwardRBFInstance
        return odict

    def __setstate__(self, dictionary):
        super(GridWithRBFInterpolator_Direct_CPU, self).__setstate__(dictionary)

    @property
    def ReverseRBFInstance(self):
        if self._ReverseRBFInstance is None:
            self._ReverseRBFInstance = super(GridWithRBFInterpolator_Direct_CPU, self).InverseInterpolator()

        return self._ReverseRBFInstance

    @property
    def ForwardRBFInstance(self):
        if self._ForwardRBFInstance is None:
            self._ForwardRBFInstance = super(GridWithRBFInterpolator_Direct_CPU, self).ForwardInterpolator()

        return self._ForwardRBFInstance

    # def InitializeDataStructures(self):
    #
    #     self._ForwardRBFInstance = cuRBFInterpolator(self.SourcePoints, self.TargetPoints)
    #     self._ReverseRBFInstance = cuRBFInterpolator(self.TargetPoints, self.SourcePoints)
    #
    #
    # def ClearDataStructures(self):
    #     """Something about the transform has changed, for example the points.
    #        Clear out our data structures so we do not use bad data"""
    #
    #     super(GridWithRBFInterpolator_Direct_CPU, self).ClearDataStructures()
    #
    #     self._ForwardRBFInstance = None
    #     self._ReverseRBFInstance = None

    def OnFixedPointChanged(self):
        super(GridWithRBFInterpolator_Direct_CPU, self).OnFixedPointChanged()
        self._ForwardRBFInstance = None
        self._ReverseRBFInstance = None

    def OnWarpedPointChanged(self):
        super(GridWithRBFInterpolator_Direct_CPU, self).OnWarpedPointChanged()
        self._ForwardRBFInstance = None
        self._ReverseRBFInstance = None

    def Transform(self, points, **kwargs):
        """
        Transform from warped space to fixed space
        :param ndarray points: [[ControlY, ControlX, MappedY, MappedX],...]
        """
        points = nornir_imageregistration.EnsurePointsAre2DNumpyArray(points)

        TransformedPoints = super(GridWithRBFInterpolator_Direct_CPU, self).Transform(points)
        return TransformedPoints

    def InverseTransform(self, points, **kwargs):
        """
        Transform from fixed space to warped space
        :param points:
        """
        points = nornir_imageregistration.EnsurePointsAre2DNumpyArray(points)

        iTransformedPoints = super(GridWithRBFInterpolator_Direct_CPU, self).InverseTransform(points)
        return iTransformedPoints

    def __init__(self, grid: ITKGridDivision):
        """
        :param ndarray pointpairs: [ControlY, ControlX, MappedY, MappedX]
        """
        self._grid = grid
        try:
            control_points = np.hstack((grid.TargetPoints, grid.SourcePoints))
        except:
            print(f'Invalid grid: {grid.TargetPoints} {grid.SourcePoints}')
            raise

        super(GridWithRBFInterpolator_Direct_CPU, self).__init__(control_points)

        self._ReverseRBFInstance = None
        self._ForwardRBFInstance = None

    @staticmethod
    def Load(TransformString: str, pixelSpacing=None):
        return nornir_imageregistration.transforms.factory.ParseGridTransform(TransformString, pixelSpacing)

class GridWithRBFInterpolator_GPU(Landmark_GPU):
    """
    classdocs
    """

    @property
    def type(self) -> TransformType:
        return TransformType.GRID

    @property
    def grid(self) -> ITKGridDivision:
        return self._grid

    @property
    def grid_dims(self) -> tuple[int, int]:
        return self._grid._grid_dims

    def ToITKString(self) -> str:
        numPoints = self.SourcePoints.shape[0]
        (bottom, left, top, right) = self.MappedBoundingBox.ToTuple()
        image_width = (
                right - left)  # We remove one because a 10x10 image is mappped from 0,0 to 10,10, which means the bounding box will be Left=0, Right=10, and width is 11 unless we correct for it.
        image_height = (top - bottom)

        YDim = int(self._grid._grid_dims[0]) - 1  # For whatever reason ITK subtracts one from the dimensions
        XDim = int(self._grid._grid_dims[1]) - 1  # For whatever reason ITK subtracts one from the dimensions

        output = ["GridTransform_double_2_2 vp " + str(numPoints * 2)]
        template = " %(cx)s %(cy)s"
        NumAdded = int(0)
        for CY, CX, MY, MX in self.points:
            pstr = template % {'cx': float_to_shortest_string(CX, 3), 'cy': float_to_shortest_string(CY, 3)}
            output.append(pstr)
            NumAdded = NumAdded + 1

        # ITK expects the image dimensions to be the actual dimensions of the image.  So if an image is 1024 pixels wide
        # then 1024 should be written to the file.
        output.append(f" fp 7 0 {YDim:d} {XDim:d} {left:g} {bottom:g} {image_width:g} {image_height:g}")
        transform_string = ''.join(output)

        return transform_string

    def __getstate__(self):

        odict = super(GridWithRBFInterpolator_GPU, self).__getstate__()
        odict['_ReverseRBFInstance'] = self._ReverseRBFInstance
        odict['_ForwardRBFInstance'] = self._ForwardRBFInstance
        odict['_discrete_transform'] = self._discrete_transform
        return odict

    def __setstate__(self, dictionary):
        super(GridWithRBFInterpolator_GPU, self).__setstate__(dictionary)

    @property
    def discrete_transform(self):
        if self._discrete_transform is None:
            self._discrete_transform = cuRegularGridInterpolator(self._grid.axis_points,
                                                                  cp.reshape(self.TargetPoints, (
                                                                      self._grid.grid_dims[0], self._grid.grid_dims[1],
                                                                      2)),
                                                                  bounds_error=False)

        return self._discrete_transform

    @property
    def ReverseRBFInstance(self):
        if self._ReverseRBFInstance is None:
            self._ReverseRBFInstance = super(GridWithRBFInterpolator_GPU, self).InverseInterpolator()

        return self._ReverseRBFInstance

    @property
    def ForwardRBFInstance(self):
        if self._ForwardRBFInstance is None:
            self._ForwardRBFInstance = super(GridWithRBFInterpolator_GPU, self).ForwardInterpolator()

        return self._ForwardRBFInstance

    def InitializeDataStructures(self):

        super(GridWithRBFInterpolator_GPU, self).InitializeDataStructures()
        # self._ForwardRBFInstance = cuRBFInterpolator(self.SourcePoints, self.TargetPoints)
        # self._ReverseRBFInstance = cuRBFInterpolator(self.TargetPoints, self.SourcePoints)

        # self._discrete_transform.InitializeDataStructures() Grid does not have an Initialize data structures call

    def ClearDataStructures(self):
        """Something about the transform has changed, for example the points.
           Clear out our data structures so we do not use bad data"""

        super(GridWithRBFInterpolator_GPU, self).ClearDataStructures()

        self._ForwardRBFInstance = None
        self._ReverseRBFInstance = None
        self._discrete_transform = None

    def OnFixedPointChanged(self):
        super(GridWithRBFInterpolator_GPU, self).OnFixedPointChanged()
        self._ForwardRBFInstance = None
        self._ReverseRBFInstance = None

    def OnWarpedPointChanged(self):
        super(GridWithRBFInterpolator_GPU, self).OnWarpedPointChanged()
        self._ForwardRBFInstance = None
        self._ReverseRBFInstance = None

    def Transform(self, points, **kwargs):
        """
        Transform from warped space to fixed space
        :param ndarray points: [[ControlY, ControlX, MappedY, MappedX],...]
        """
        print("GridWithRBFInterpolator_GPU -> TRANSFORM()")
        points = nornir_imageregistration.EnsurePointsAre2DCuPyArray(points)

        if points.shape[0] == 0:
            return cp.empty((0, 2), dtype=points.dtype)

        TransformedPoints = self._discrete_transform.Transform(points)
        extrapolate = kwargs.get('extrapolate', True)
        if not extrapolate:
            return TransformedPoints

        (GoodPoints, InvalidIndicies, ValidIndicies) = utils.InvalidIndicies_GPU(TransformedPoints)

        if len(InvalidIndicies) == 0:
            return TransformedPoints
        else:
            if len(points) > 1:
                # print InvalidIndicies;
                BadPoints = points[InvalidIndicies]
            else:
                BadPoints = points

        # BadPoints = cp.asarray(BadPoints, dtype=np.float32)
        if not (BadPoints.dtype == np.float32 or BadPoints.dtype == np.float64):
            BadPoints = cp.asarray(BadPoints, dtype=np.float32)

        FixedPoints = super(GridWithRBFInterpolator_GPU, self).Transform(BadPoints)

        TransformedPoints[InvalidIndicies] = FixedPoints
        return TransformedPoints

    def InverseTransform(self, points, **kwargs):
        """
        Transform from fixed space to warped space
        :param points:
        """
        print("GridWithRBFInterpolator_GPU -> INVERSETRANSFORM()")
        points = nornir_imageregistration.EnsurePointsAre2DCuPyArray(points)

        iTransformedPoints = super(GridWithRBFInterpolator_GPU, self).InverseTransform(points)
        return iTransformedPoints

    def __init__(self, grid: ITKGridDivision):
        """
        :param ndarray pointpairs: [ControlY, ControlX, MappedY, MappedX]
        """
        self._grid = grid
        try:
            control_points = cp.hstack((grid.TargetPoints, grid.SourcePoints))
        except:
            print(f'Invalid grid: {grid.TargetPoints} {grid.SourcePoints}')
            raise

        super(GridWithRBFInterpolator_GPU, self).__init__(control_points)
        self._discrete_transform = cuRegularGridInterpolator(self._grid.axis_points,
                                                                cp.reshape(self._grid.TargetPoints, (
                                                                self._grid.grid_dims[0], self._grid.grid_dims[1], 2)),
                                                                bounds_error=False)
        self._ReverseRBFInstance = None
        self._ForwardRBFInstance = None

    @staticmethod
    def Load(TransformString: str, pixelSpacing=None):
        return nornir_imageregistration.transforms.factory.ParseGridTransform(TransformString, pixelSpacing)

class GridWithRBFInterpolator_CPU(Landmark_CPU):
    """
    classdocs
    """

    @property
    def type(self) -> TransformType:
        return TransformType.GRID

    @property
    def grid(self) -> ITKGridDivision:
        return self._grid

    @property
    def grid_dims(self) -> tuple[int, int]:
        return self._grid._grid_dims

    def ToITKString(self) -> str:
        numPoints = self.SourcePoints.shape[0]
        (bottom, left, top, right) = self.MappedBoundingBox.ToTuple()
        image_width = (
                right - left)  # We remove one because a 10x10 image is mappped from 0,0 to 10,10, which means the bounding box will be Left=0, Right=10, and width is 11 unless we correct for it.
        image_height = (top - bottom)

        YDim = int(self._grid._grid_dims[0]) - 1  # For whatever reason ITK subtracts one from the dimensions
        XDim = int(self._grid._grid_dims[1]) - 1  # For whatever reason ITK subtracts one from the dimensions

        output = ["GridTransform_double_2_2 vp " + str(numPoints * 2)]
        template = " %(cx)s %(cy)s"
        NumAdded = int(0)
        for CY, CX, MY, MX in self.points:
            pstr = template % {'cx': float_to_shortest_string(CX, 3), 'cy': float_to_shortest_string(CY, 3)}
            output.append(pstr)
            NumAdded = NumAdded + 1

        # ITK expects the image dimensions to be the actual dimensions of the image.  So if an image is 1024 pixels wide
        # then 1024 should be written to the file.
        output.append(f" fp 7 0 {YDim:d} {XDim:d} {left:g} {bottom:g} {image_width:g} {image_height:g}")
        transform_string = ''.join(output)

        return transform_string

    def __getstate__(self):

        odict = super(GridWithRBFInterpolator_CPU, self).__getstate__()
        odict['_ReverseRBFInstance'] = self._ReverseRBFInstance
        odict['_ForwardRBFInstance'] = self._ForwardRBFInstance
        odict['_discrete_transform'] = self._discrete_transform
        return odict

    def __setstate__(self, dictionary):
        super(GridWithRBFInterpolator_CPU, self).__setstate__(dictionary)

    @property
    def discrete_transform(self):
        if self._discrete_transform is None:
            self._discrete_transform = RegularGridInterpolator(self._grid.axis_points,
                                                                  np.reshape(self.TargetPoints, (
                                                                      self._grid.grid_dims[0], self._grid.grid_dims[1],
                                                                      2)),
                                                                  bounds_error=False)

        return self._discrete_transform

    @property
    def ReverseRBFInstance(self):
        if self._ReverseRBFInstance is None:
            self._ReverseRBFInstance = super(GridWithRBFInterpolator_CPU, self).InverseInterpolator()

        return self._ReverseRBFInstance

    @property
    def ForwardRBFInstance(self):
        if self._ForwardRBFInstance is None:
            self._ForwardRBFInstance = super(GridWithRBFInterpolator_CPU, self).ForwardInterpolator()

        return self._ForwardRBFInstance

    def InitializeDataStructures(self):

        super(GridWithRBFInterpolator_CPU, self).InitializeDataStructures()
        # self._ForwardRBFInstance = cuRBFInterpolator(self.SourcePoints, self.TargetPoints)
        # self._ReverseRBFInstance = cuRBFInterpolator(self.TargetPoints, self.SourcePoints)

        # self._discrete_transform.InitializeDataStructures() Grid does not have an Initialize data structures call

    def ClearDataStructures(self):
        """Something about the transform has changed, for example the points.
           Clear out our data structures so we do not use bad data"""

        super(GridWithRBFInterpolator_CPU, self).ClearDataStructures()

        self._ForwardRBFInstance = None
        self._ReverseRBFInstance = None
        self._discrete_transform = None

    def OnFixedPointChanged(self):
        super(GridWithRBFInterpolator_CPU, self).OnFixedPointChanged()
        self._ForwardRBFInstance = None
        self._ReverseRBFInstance = None

    def OnWarpedPointChanged(self):
        super(GridWithRBFInterpolator_CPU, self).OnWarpedPointChanged()
        self._ForwardRBFInstance = None
        self._ReverseRBFInstance = None

    def Transform(self, points, **kwargs):
        """
        Transform from warped space to fixed space
        :param ndarray points: [[ControlY, ControlX, MappedY, MappedX],...]
        """
        print("GridWithRBFInterpolator_CPU -> TRANSFORM()")
        points = nornir_imageregistration.EnsurePointsAre2DNumpyArray(points)

        if points.shape[0] == 0:
            return np.empty((0, 2), dtype=points.dtype)

        TransformedPoints = self._discrete_transform.Transform(points)
        extrapolate = kwargs.get('extrapolate', True)
        if not extrapolate:
            return TransformedPoints

        (GoodPoints, InvalidIndicies, ValidIndicies) = utils.InvalidIndicies(TransformedPoints)

        if len(InvalidIndicies) == 0:
            return TransformedPoints
        else:
            if len(points) > 1:
                # print InvalidIndicies;
                BadPoints = points[InvalidIndicies]
            else:
                BadPoints = points

        if not (BadPoints.dtype == np.float32 or BadPoints.dtype == np.float64):
            BadPoints = np.asarray(BadPoints, dtype=np.float32)

        FixedPoints = super(GridWithRBFInterpolator_CPU, self).Transform(BadPoints)

        TransformedPoints[InvalidIndicies] = FixedPoints
        return TransformedPoints

    def InverseTransform(self, points, **kwargs):
        """
        Transform from fixed space to warped space
        :param points:
        """
        print("GridWithRBFInterpolator_CPU -> INVERSETRANSFORM()")
        points = nornir_imageregistration.EnsurePointsAre2DNumpyArray(points)

        iTransformedPoints = super(GridWithRBFInterpolator_CPU, self).InverseTransform(points)
        return iTransformedPoints

    def __init__(self, grid: ITKGridDivision):
        """
        :param ndarray pointpairs: [ControlY, ControlX, MappedY, MappedX]
        """
        self._grid = grid
        try:
            control_points = np.hstack((grid.TargetPoints, grid.SourcePoints))
        except:
            print(f'Invalid grid: {grid.TargetPoints} {grid.SourcePoints}')
            raise

        super(GridWithRBFInterpolator_CPU, self).__init__(control_points)
        self._discrete_transform = RegularGridInterpolator(self._grid.axis_points,
                                                                np.reshape(self._grid.TargetPoints, (
                                                                self._grid.grid_dims[0], self._grid.grid_dims[1], 2)),
                                                                bounds_error=False)
        self._ReverseRBFInstance = None
        self._ForwardRBFInstance = None

    @staticmethod
    def Load(TransformString: str, pixelSpacing=None):
        return nornir_imageregistration.transforms.factory.ParseGridTransform(TransformString, pixelSpacing)

if __name__ == '__main__':
    p = np.array([[0, 0, 0, 0],
                     [0, 10, 0, -10],
                     [10, 0, -10, 0],
                     [10, 10, -10, -10]])

    (Fixed, Moving) = np.hsplit(p, 2)
    T = OneWayRBFWithLinearCorrection(Fixed, Moving)

    warpedPoints = [[0, 0], [-5, -5]]
    fp = T.ViewTransform(warpedPoints)
    print(("__Transform " + str(warpedPoints) + " to " + str(fp)))
    wp = T.InverseTransform(fp)

    print("Fixed Verts")
    print(T.FixedTriangles)
    print("\nWarped Verts")
    print(T.WarpedTriangles)

    T.AddPoint([5, 5, -5, -5])
    print("\nPoint added")
    print("Fixed Verts")
    print(T.FixedTriangles)
    print("\nWarped Verts")
    print(T.WarpedTriangles)

    T.AddPoint([5, 5, 5, 5])
    print("\nDuplicate Point added")
    print("Fixed Verts")
    print(T.FixedTriangles)
    print("\nWarped Verts")
    print(T.WarpedTriangles)

    warpedPoint = [[-5, -5]]
    fp = T.ViewTransform(warpedPoint)
    print(("__Transform " + str(warpedPoint) + " to " + str(fp)))
    wp = T.InverseTransform(fp)

    T.UpdatePoint(3, [10, 15, -10, -15])
    print("\nPoint updated")
    print("Fixed Verts")
    print(T.FixedTriangles)
    print("\nWarped Verts")
    print(T.WarpedTriangles)

    warpedPoint = [[-9, -14]]
    fp = T.ViewTransform(warpedPoint)
    print(("__Transform " + str(warpedPoint) + " to " + str(fp)))
    wp = T.InverseTransform(fp)

    T.RemovePoint(1)
    print("\nPoint removed")
    print("Fixed Verts")
    print(T.FixedTriangles)
    print("\nWarped Verts")
    print(T.WarpedTriangles)

    print("\nFixedPointsInRect")
    print(T.GetFixedPointsRect([-1, -1, 14, 4]))
