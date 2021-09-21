'''
Created on Nov 13, 2012

@author: u0490822

The factory is focused on the loading and saving of transforms
'''

from scipy import *

from nornir_imageregistration.spatial.indicies import *
from nornir_imageregistration.spatial import Rectangle 
import nornir_imageregistration.transforms
import numpy as np

from . import utils


def TransformToIRToolsString(transformObj, bounds=None):
    if hasattr(transformObj, 'gridWidth') and hasattr(transformObj, 'gridHeight'):
        return _TransformToIRToolsGridString(transformObj, transformObj.gridWidth, transformObj.gridHeight, bounds=bounds)
    if isinstance(transformObj, nornir_imageregistration.transforms.RigidNoRotation):
        return transformObj.ToITKString()
    else:
        return _TransformToIRToolsString(transformObj, bounds)  # , bounds=NewStosFile.MappedImageDim)

    
def _GetMappedBoundsExtents(transform, bounds=None):
    # Find the extent of the mapped boundaries
    (bottom, left, top, right) = (None, None, None, None)
    if bounds is None:
        (bottom, left, top, right) = transform.MappedBoundingBox.ToTuple()
    elif isinstance(bounds, Rectangle):
        (bottom, left, top, right) = bounds.BoundingBox
    else:
        (bottom, left, top, right) = bounds
    
    return (bottom, left, top, right)
 

def float_to_shortest_string(val, precision=6):
    '''
    Convert a floating point value to the shortest string possible
    '''
    format_spec = '''{0:0.''' + str(precision) + '''f}'''
    return format_spec.format(val).rstrip('0').rstrip('.')

    
def _TransformToIRToolsGridString(Transform, XDim, YDim, bounds=None):

    numPoints = Transform.points.shape[0]

    # Find the extent of the mapped boundaries
    (bottom, left, top, right) = _GetMappedBoundsExtents(Transform, bounds)

    output = []
    output.append("GridTransform_double_2_2 vp " + str(numPoints * 2))
     
    # template = " %(cx).3f %(cy).3f"
    template = " %(cx)s %(cy)s"

    NumAdded = int(0) 
    for CY, CX, MY, MX in Transform.points:
        pstr = template % {'cx' : float_to_shortest_string(CX, 3), 'cy' : float_to_shortest_string(CY, 3)}
        output.append(pstr)
        NumAdded = NumAdded + 1

   # print str(NumAdded) + " points added"

    boundsStr = " ".join(map(str, [left, bottom, right - left, top - bottom]))
    
    output.append(" fp 7 0 " + str(int(YDim - 1)) + " " + str(int(XDim - 1)) + " " + boundsStr)
    # output = output + " fp 7 0 " + str(int(YDim - 1)) + " " + str(int(XDim - 1)) + " " + boundsStr
    transform_string = ''.join(output)
    
    return transform_string


def _TransformToIRToolsString(Transform, bounds=None):
    numPoints = Transform.points.shape[0]

    # Find the extent of the mapped boundaries
    (bottom, left, top, right) = _GetMappedBoundsExtents(Transform, bounds)

    output = []
    output.append("MeshTransform_double_2_2 vp " + str(numPoints * 4))

    # template = " %(mx).10f %(my).10f %(cx).3f %(cy).3f"
    template = " %(mx)s %(my)s %(cx)s %(cy)s"

    width = right - left
    height = top - bottom

    for CY, CX, MY, MX in Transform.points:
        pstr = template % {'cx' : float_to_shortest_string(CX, 3),
                           'cy' : float_to_shortest_string(CY, 3),
                           'mx' : float_to_shortest_string((MX - left) / width, 10),
                           'my' : float_to_shortest_string((MY - bottom) / height, 10)}
        output.append(pstr)

    boundsStr = " ".join(map(str, [left, bottom, width, height]))
    
    output.append(" fp 8 0 16 16 ")
    output.append(boundsStr)
    output.append(' ' + str(numPoints))
    
    # boundsStr = " ".join(map(str, [0, 0, width, height]))
    # transform_string = #output + " fp 8 0 16 16 " + boundsStr + ' ' + str(numPoints)
    transform_string = ''.join(output)

    return transform_string


def __ParseParameters(parts):
    '''Input is a transform split on white space, returns the variable and fixed parameters as a list'''

    iVP = 0
    iFP = 0

    VariableParameters = []
    FixedParameters = []

    for i, val in enumerate(parts):
        if val == 'vp':
            iVP = i
        elif val == 'fp':
            iFP = i
        elif iFP > 0 and i > iFP + 1:
            FixedParameters.append(float(val))
            if FixedParameters[-1] >= 1.79769e+308:
                raise ValueError("Unexpected value in transform, probably invalid output from ir-tools")

        elif iVP > 0 and i > iVP + 1:
            VariableParameters.append(float(val))
            if VariableParameters[-1] >= 1.79769e+308:
                raise ValueError("Unexpected value in transform, probably invalid output from ir-tools")

    return (VariableParameters, FixedParameters)


def SplitTrasform(transformstring):
    '''Returns transform name, variable points, fixed points'''
    parts = transformstring.split()
    transformName = parts[0]
    assert(parts[1] == 'vp')

    VariableParts = []
    iVp = 2
    while(parts[iVp] != 'fp'):
        VariableParts = float(parts[iVp])
        iVp = iVp + 1

    # skip vp # entries
    iVp = iVp + 2
    FixedParts = []
    for iVp in range(iVp, len(parts)):
        FixedParts = float(parts[iVp])

    return (transformName, FixedParts, VariableParts)


def LoadTransform(Transform, pixelSpacing=None):
    '''Transform is a string from either a stos or mosiac file'''

    parts = Transform.split()

    transformType = parts[0]

    if transformType == "GridTransform_double_2_2":
        return ParseGridTransform(parts, pixelSpacing)
    elif transformType == "MeshTransform_double_2_2":
        return ParseMeshTransform(parts, pixelSpacing)
    elif transformType == "LegendrePolynomialTransform_double_2_2_1":
        return ParseLegendrePolynomialTransform(parts, pixelSpacing)
    elif transformType == "Rigid2DTransform_double_2_2":
        return ParseRigid2DTransform(parts, pixelSpacing)
    elif transformType == "CenteredSimilarity2DTransform_double_2_2":
        return ParseCenteredSimilarity2DTransform(parts, pixelSpacing)
    
    raise ValueError("LoadTransform was passed an unknown transform type")


def ParseGridTransform(parts, pixelSpacing=None):

    if pixelSpacing is None:
        pixelSpacing = 1.0

    (VariableParameters, FixedParameters) = __ParseParameters(parts)

    gridWidth = int(FixedParameters[2]) + 1
    gridHeight = int(FixedParameters[1]) + 1

    ImageWidth = float(FixedParameters[5]) * pixelSpacing
    ImageHeight = float(FixedParameters[6]) * pixelSpacing

    PointPairs = []

    for i in range(0, len(VariableParameters) - 1, 2):
        iY = (i / 2) // gridWidth
        iX = (i / 2) % gridWidth

        mappedX = (float(iX) / float(gridWidth - 1)) * ImageWidth
        mappedY = (float(iY) / float(gridHeight - 1)) * ImageHeight
        ControlX = VariableParameters[i]
        ControlY = VariableParameters[i + 1]
        PointPairs.append((ControlY, ControlX, mappedY, mappedX))

    T = nornir_imageregistration.transforms.MeshWithRBFFallback(PointPairs)
    T.gridWidth = gridWidth
    T.gridHeight = gridHeight
    return T


def ParseMeshTransform(parts, pixelSpacing=None):

    if pixelSpacing is None:
        pixelSpacing = 1.0

    (VariableParameters, FixedParameters) = __ParseParameters(parts)

    Left = float(FixedParameters[3]) * pixelSpacing
    Bottom = float(FixedParameters[4]) * pixelSpacing
    ImageWidth = float(FixedParameters[5]) * pixelSpacing
    ImageHeight = float(FixedParameters[6]) * pixelSpacing

    PointPairs = []

    for i in range(0, len(VariableParameters) - 1, 4):

        mappedX = (VariableParameters[i + 0] * ImageWidth) + Left
        mappedY = (VariableParameters[i + 1] * ImageHeight) + Bottom
        ControlX = float(VariableParameters[i + 2]) * pixelSpacing
        ControlY = float(VariableParameters[i + 3]) * pixelSpacing

        PointPairs.append((ControlY, ControlX, mappedY, mappedX))

    T = nornir_imageregistration.transforms.MeshWithRBFFallback(PointPairs)
    return T


def ParseLegendrePolynomialTransform(parts, pixelSpacing=None):

    # Example: LegendrePolynomialTransform_double_2_2_1 vp 6 1 0 1 1 1 0 fp 4 10770 -10770 2040 2040

    if pixelSpacing is None:
        pixelSpacing = 1.0

    (VariableParameters, FixedParameters) = __ParseParameters(parts)

    # We don't support anything but translation from this transform at the moment:
    # assert(VariableParameters == [1, 0, 1, 1, 1, 0])  # Sequence for transform only transformation

    Left = 0 * pixelSpacing
    Bottom = 0 * pixelSpacing
    ImageWidth = float(FixedParameters[2]) * pixelSpacing * 2.0
    ImageHeight = float(FixedParameters[3]) * pixelSpacing * 2.0

    array = np.array([[Left, Bottom],
                  [Left, Bottom + ImageHeight],
                  [Left + ImageWidth, Bottom],
                  [Left + ImageWidth, Bottom + ImageHeight]])
    PointPairs = []

    for i in range(0, 4):
        mappedX, mappedY = array[i, :]
        ControlX = (FixedParameters[0] * pixelSpacing) + mappedX
        ControlY = (FixedParameters[1] * pixelSpacing) + mappedY
        PointPairs.append((ControlY, ControlX, mappedY, mappedX))

    T = nornir_imageregistration.transforms.MeshWithRBFFallback(PointPairs)
    return T


def ParseRigid2DTransform(parts, pixelSpacing=None):

    # Example: Rigid2DTransform_double_2_2 vp 3 0 0 0 fp 2 0 0
    if pixelSpacing is None:
        pixelSpacing = 1.0

    (VariableParameters, FixedParameters) = __ParseParameters(parts)

    angle = float(VariableParameters[0])
    xoffset = float(VariableParameters[1])
    yoffset = float(VariableParameters[2])
    
    x_center = float(FixedParameters[0])
    y_center = float(FixedParameters[1])
    
    return nornir_imageregistration.transforms.Rigid(target_offset=(yoffset, xoffset), source_center=(y_center, x_center), angle=angle)

def ParseCenteredSimilarity2DTransform(parts, pixelSpacing=None):

    # Example: CenteredSimilarity2DTransform_double_2_2 vp 6 0 0 0 0 0 0
    if pixelSpacing is None:
        pixelSpacing = 1.0

    (VariableParameters, FixedParameters) = __ParseParameters(parts)

    scale = float(VariableParameters[0])
    angle = float(VariableParameters[1])
    x_center = float(FixedParameters[2])
    y_center = float(FixedParameters[3])
    xoffset = float(VariableParameters[4])
    yoffset = float(VariableParameters[5])
    
    return nornir_imageregistration.transforms.CenteredSimilarity2DTransform(target_offset=(yoffset, xoffset),
                                                                             source_center=(y_center, x_center),
                                                                             angle=angle,
                                                                             scale=scale)


def __CorrectOffsetForMismatchedImageSizes(offset, FixedImageShape, MovingImageShape, scale=1.0):
    '''
    :param float scale: Scale the movingImageShape by this amount before correcting to match scaling done to the moving image when passed to the registration algorithm
    '''
    
    if isinstance(scale, float):
        scale = (scale, scale)
    elif hasattr(scale, '__iter__') == False:
        raise NotImplementedError("Unsupported type")
    
    return (offset[0] + ((FixedImageShape[0] - MovingImageShape[0] * scale[0]) / 2.0), offset[1] + ((FixedImageShape[1] - MovingImageShape[1] * scale[1]) / 2.0))


def CreateRigidTransform(warped_offset, rangle, target_image_shape, source_image_shape, flip_ud=False):
    '''Returns a transform, the fixed image defines the boundaries of the transform.
       The warped image '''

    use_mesh_transform = flip_ud
    scalar = 1.0
    source_image_shape = nornir_imageregistration.EnsurePointsAre1DNumpyArray(source_image_shape)
    target_image_shape = nornir_imageregistration.EnsurePointsAre1DNumpyArray(target_image_shape)
    
#     if not np.array_equal(source_image_shape, target_image_shape):
#         shape_ratio = target_image_shape.astype(np.float64) / source_image_shape.astype(np.float64) 
#         if shape_ratio[0] != shape_ratio[1]: 
#             use_mesh_transform = True
#         else:
#             scalar = shape_ratio[0]
            
    if use_mesh_transform:
        return CreateRigidMeshTransform(FixedImageSize=target_image_shape,
                                        WarpedImageSize=source_image_shape,
                                        rangle=rangle,
                                        warped_offset=warped_offset,
                                        flip_ud=flip_ud)
        
    
    assert(source_image_shape[0] > 0)
    assert(source_image_shape[1] > 0)
    assert(target_image_shape[0] > 0)
    assert(target_image_shape[1] > 0)
    
    source_rotation_center = (source_image_shape) / 2.0

    # Adjust offset for any mismatch in dimensions
    #Adjust the center of rotation to be consistent with the original ir-tools
    AdjustedOffset = __CorrectOffsetForMismatchedImageSizes(warped_offset, target_image_shape, source_image_shape)

    # The offset is the translation of the warped image over the fixed image.  If we translate 0,0 from the warped space into
    # fixed space we should obtain the warped_offset value
    # TargetPoints = GetTransformedRigidCornerPoints(WarpedImageSize, rangle, AdjustedOffset)
    # SourcePoints = GetTransformedRigidCornerPoints(WarpedImageSize, rangle=0, offset=(0, 0), flip_ud=flip_ud)

    # ControlPoints = np.append(TargetPoints, SourcePoints, 1)

    transform = nornir_imageregistration.transforms.CenteredSimilarity2DTransform(target_offset=AdjustedOffset,
                                                          source_rotation_center=source_rotation_center,
                                                          angle=rangle,
                                                          scalar=scalar,
                                                          MappedBoundingBox=nornir_imageregistration.Rectangle.CreateFromPointAndArea((0,0),source_image_shape))

    return transform


def CreateRigidMeshTransform(target_image_shape, source_image_shape, rangle, warped_offset, flip_ud=False, scale=1.0):
    '''
    Returns a MeshWithRBFFallback transform, the fixed image defines the boundaries of the transform.
    '''
    source_image_shape = nornir_imageregistration.EnsurePointsAre1DNumpyArray(source_image_shape)
    target_image_shape = nornir_imageregistration.EnsurePointsAre1DNumpyArray(target_image_shape)
    
    assert(source_image_shape[0] > 0)
    assert(source_image_shape[1] > 0)
    assert(target_image_shape[0] > 0)
    assert(target_image_shape[1] > 0)

    # Adjust offset for any mismatch in dimensions
    #Adjust the center of rotation to be consistent with the original ir-tools
    AdjustedOffset = __CorrectOffsetForMismatchedImageSizes(warped_offset, target_image_shape, source_image_shape, scale)     

    # The offset is the translation of the warped image over the fixed image.  If we translate 0,0 from the warped space into
    # fixed space we should obtain the warped_offset value
    TargetPoints = GetTransformedRigidCornerPoints(source_image_shape, rangle, AdjustedOffset, scale=scale)
    SourcePoints = GetTransformedRigidCornerPoints(source_image_shape, rangle=0, offset=(0, 0), flip_ud=flip_ud)

    ControlPoints = np.append(TargetPoints, SourcePoints, 1)

    transform = nornir_imageregistration.transforms.MeshWithRBFFallback(ControlPoints)

    return transform


def GetTransformedRigidCornerPoints(size, rangle, offset, flip_ud=False, scale=1.0):
    '''Returns positions of the four corners of a warped image in a fixed space using the rotation and peak offset.  Rotation occurs at the center.
       Flip, if requested, is performed before the rotation and translation
    :param tuple size: (Height, Width)
    :param float rangle: Angle in radians
    :param tuple offset: (Y, X)
    :param float scale: Scale the corners by this factor. Ex: 0.5 produces points that shrink the source space by 50% in target space.
    :return: Nx2 array of points [[BotLeft], [BotRight], [TopLeft],  [TopRight]]
    :rtype: numpy.ndarray
    '''
    
    #The corners of a X,Y image that starts at 0,0 are located at X-1,Y-1.  So we subtract one from the size
    size = size - np.array((1,1))
    CenteredRotation = utils.RotationMatrix(rangle)
    
    ScaleMatrix = None
    if scale is not None:
        ScaleMatrix = utils.ScaleMatrixXY(scale)
    else:
        ScaleMatrix = np.identity(3)

    HalfWidth = (size[iArea.Width]) / 2.0
    HalfHeight = (size[iArea.Height]) / 2.0

#     BotLeft = CenteredRotation * matrix([[-HalfWidth], [-HalfHeight], [1]])
#     TopLeft = CenteredRotation * matrix([[-HalfWidth], [HalfHeight], [1]])
#     BotRight = CenteredRotation * matrix([[HalfWidth], [-HalfHeight], [1]])
#     TopRight = CenteredRotation * matrix([[HalfWidth], [HalfHeight], [1]])

    if not flip_ud:
        BotLeft = CenteredRotation * matrix([[-HalfHeight], [-HalfWidth], [1]])
        TopLeft = CenteredRotation * matrix([[HalfHeight], [-HalfWidth], [1]])
        BotRight = CenteredRotation * matrix([[-HalfHeight], [HalfWidth], [1]])
        TopRight = CenteredRotation * matrix([[HalfHeight], [HalfWidth], [1]])
    else:
        BotLeft = CenteredRotation * matrix([[HalfHeight], [-HalfWidth], [1]])
        TopLeft = CenteredRotation * matrix([[-HalfHeight], [-HalfWidth], [1]])
        BotRight = CenteredRotation * matrix([[HalfHeight], [HalfWidth], [1]])
        TopRight = CenteredRotation * matrix([[-HalfHeight], [HalfWidth], [1]])
        
    # Adjust to the peak location
    PeakTranslation = matrix([[1, 0, offset[iPoint.Y]], [0, 1, offset[iPoint.X]], [0, 0, 1]])

    BotLeft = PeakTranslation * BotLeft
    TopLeft = PeakTranslation * TopLeft
    BotRight = PeakTranslation * BotRight
    TopRight = PeakTranslation * TopRight

    #Center the image
    Translation = matrix([[1, 0, HalfHeight], [0, 1, HalfWidth], [0, 0, 1]])

    BotLeft = Translation * BotLeft
    BotRight = Translation * BotRight
    TopLeft = Translation * TopLeft
    TopRight = Translation * TopRight
    
    #scale the output
    BotLeft = ScaleMatrix * BotLeft
    BotRight = ScaleMatrix * BotRight
    TopLeft = ScaleMatrix * TopLeft
    TopRight = ScaleMatrix * TopRight

    

    arr = np.vstack([BotLeft[:2].getA1(), BotRight[:2].getA1(), TopLeft[:2].getA1(), TopRight[:2].getA1()])
    # arr[:, [0, 1]] = arr[:, [1, 0]]  # Swapped when GetTransformedCornerPoints switched to Y,X points
    return arr
