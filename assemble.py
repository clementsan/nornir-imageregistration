'''
Created on Apr 22, 2013

@author: u0490822
'''


import core
import numpy as np
import Utils.PrettyOutput as PrettyOutput
import Utils.Images
from scipy.ndimage import interpolation
from   IrTools.Transforms import factory
from   IrTools.Transforms import triangulation
from IrTools.Transforms import utils
import IrTools.Transforms.base as transformbase
from IrTools.IO.stosfile import StosFile
import os
import Pools

from pylab import imsave


def ROI(botleft, area):
    x_range = range(int(botleft[1]), int(botleft[1]) + int(area[1]))
    y_range = range(int(botleft[0]), int(botleft[0]) + int(area[0]))

    i_y, i_x = np.meshgrid(y_range, x_range, sparse=False, indexing='ij')

    coordArray = np.vstack((i_y.flat, i_x.flat)).transpose()

    return coordArray

def TransformROI(transform, botleft, area):
    '''Apply a transform to an image ROI, center and area are in fixed space
       Returns an array of indicies into the warped image'''

    fixed_coordArray = ROI(botleft, area)

    warped_coordArray = transform.InverseTransform(fixed_coordArray)
    (valid_warped_coordArray, InvalidIndicies) = utils.InvalidIndicies(warped_coordArray)

    valid_fixed_coordArray = np.delete(fixed_coordArray, InvalidIndicies, axis=0)


    valid_fixed_coordArray = valid_fixed_coordArray - botleft

    return (valid_fixed_coordArray, valid_warped_coordArray)


def FixedImage(image, botleft=None, area=None):
    '''Extract a region from an image'''
    if botleft is None:
        botleft = (0, 0)

    if area is None:
        area = image.shape

    coords = ROI(botleft, area)

    transformedImage = interpolation.map_coordinates(image, coords.transpose(), order=0, mode='constant')

    transformedImage = transformedImage.reshape(area)
    return transformedImage


def WarpedImageToFixedSpace(transform, FixedImageArea, WarpedImage, botleft=None, area=None):

    if botleft is None:
        botleft = (0, 0)

    if area is None:
        area = FixedImageArea

    (fixed_coords, warped_coords) = TransformROI(transform, botleft, area)
    if(warped_coords.shape[0] == 0):
        transformedImage = np.zeros((area))
        return transformedImage

    minCoord = np.floor(np.min(warped_coords, 0)) - np.array([1, 1])
    maxCoord = np.ceil(np.max(warped_coords, 0)) + np.array([1, 1])

    subroi_warpedImage = WarpedImage
    if area[0] <= FixedImageArea[0] and area[1] <= FixedImageArea[1]:
        subroi_warpedImage = FixedImage(WarpedImage, minCoord, (maxCoord - minCoord))
        warped_coords = warped_coords - minCoord


    warpedImage = interpolation.map_coordinates(subroi_warpedImage, warped_coords.transpose(), mode='constant')
    if fixed_coords.shape[0] == np.prod(area):
        # All coordinates mapped, so we can return the output warped image as is.
        warpedImage = warpedImage.reshape(area)
        return warpedImage
    else:
        # Not all coordinates mapped, create an image of the correct size and place the warped image inside it.
        transformedImage = np.zeros((area))
        transformedImage[fixed_coords[:, 0], fixed_coords[:, 1]] = warpedImage
        return transformedImage


def TransformStos(transformData, OutputFilename=None, fixedImageFilename=None, warpedImageFilename=None, scalar=1.0, CropUndefined=False):
    '''Assembles an image based on the passed transform.
       Discreet = True causes points outside the defined transform region to be clipped instead of interpolated'''

    stos = None
    if isinstance(transformData, str):
        if not os.path.exists(transformData):
            return None;

        stos = StosFile.Load(transformData)
        stostransform = factory.LoadTransform(stos.Transform)
    elif isinstance(transformData, StosFile):
        stos = transformData.Transform
        stostransform = factory.LoadTransform(stos.Transform)
    elif isinstance(transformData, transformbase.Base):
        stostransform = transformData

    if CropUndefined:
        stostransform = triangulation.Triangulation(pointpairs=stostransform.points)

    if fixedImageFilename is None:
        if stos is None:
            return None

        fixedImageFilename = stos.ControlImageFullPath

    if warpedImageFilename is None:
        if stos is None:
            return None

        warpedImageFilename = stos.MappedImageFullPath

    fixedImageSize = Utils.Images.GetImageSize(fixedImageFilename)
    fixedImageShape = np.array([fixedImageSize[1], fixedImageSize[0]]) * scalar
    warpedImage = core.LoadImage(warpedImageFilename)

    stostransform.points = stostransform.points * scalar

    warpedImage = TransformImage(stostransform, fixedImageShape, warpedImage)

    if not OutputFilename is None:
        imsave(OutputFilename, warpedImage, cmap='gray')

    return warpedImage


def TransformImage(transform, fixedImageShape, warpedImage):
    '''Cut image into tiles, assemble small chunks'''

    tilesize = [2048, 2048]

    height = int(fixedImageShape[0])
    width = int(fixedImageShape[1])

    outputImage = np.zeros(fixedImageShape, dtype=np.float32)

    # print('\nConverting image to ' + str(self.NumCols) + "x" + str(self.NumRows) + ' grid of OpenGL textures')

    tasks = []

    mpool = Pools.GetGlobalMultithreadingPool()

    for iY in range(0, height, int(tilesize[0])):

        end_iY = iY + tilesize[0]
        if end_iY > height:
            end_iY = height

        for iX in range(0, width, int(tilesize[1])):

            end_iX = iX + tilesize[1]
            if end_iX > width:
                end_iX = width

            task = mpool.add_task(str(iX) + "x_" + str(iY) + "y", WarpedImageToFixedSpace, transform, fixedImageShape, warpedImage, botleft=[iY, iX], area=[end_iY - iY, end_iX - iX])
            task.iY = iY
            task.end_iY = end_iY
            task.iX = iX
            task.end_iX = end_iX

            tasks.append(task)

            # registeredTile = WarpedImageToFixedSpace(transform, fixedImageShape, warpedImage, botleft=[iY, iX], area=[end_iY - iY, end_iX - iX])
            # outputImage[iY:end_iY, iX:end_iX] = registeredTile

    for task in tasks:
        registeredTile = task.wait_return()
        outputImage[task.iY:task.end_iY, task.iX:task.end_iX] = registeredTile

    return outputImage
