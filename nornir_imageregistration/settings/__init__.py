import json

from .grid_refinement import GridRefinement
from .mosaic_tile_offset import TileOffset, LoadMosaicOffsets, SaveMosaicOffsets
from .translate import TranslateSettings


def GetOrSaveTranslateSettings(settings: TranslateSettings, path: str):
    '''
    Check if a .json file exists, if it does load and return it.  Otherwise 
    save the provide settings file as a .json file 
    '''
    try:
        with open(path, 'r') as jsonfile:
            data = json.load(jsonfile)
            return TranslateSettings(**data)
    except:
        with open(path, 'w') as jsonfile:
            json.dump(settings.__dict__, jsonfile, sort_keys=True, indent=2)
        return settings
