#!/usr/bin/env python
###############################################################################
# $Id$
#
# Project:  OGR Python samples
# Purpose:  Assemble TIGER Polygons.
# Author:   Frank Warmerdam, warmerdam@pobox.com
#
###############################################################################
# Copyright (c) 2003, Frank Warmerdam <warmerdam@pobox.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
# OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.
###############################################################################
#
#  $Log$
#  Revision 1.5  2005/07/29 04:49:46  fwarmerdam
#  Set SRS on generated file.
#  http://bugzilla.remotesensing.org/show_bug.cgi?id=644
#
#  Revision 1.4  2004/10/30 20:54:42  fwarmerdam
#  Applied patch from Schuyler Erle (bug 646) to discard dangles and
#  degenerate rings.
#
#  Revision 1.3  2003/07/11 14:52:13  warmerda
#  Added logic to replicate all source polygon fields onto output file.
#
#  Revision 1.2  2003/07/11 14:31:17  warmerda
#  Use provided input filename.
#
#  Revision 1.1  2003/03/03 05:17:06  warmerda
#  New
#
#

import osr
import ogr
import string
import sys


#############################################################################
def tiger_to_tract(infile):
    class Module:

        def __init__( self ):
            self.lines = {}
            self.poly_line_links = {}
#############################################################################
# Argument processing.

    outfile = 'poly.shp'

    #############################################################################
    # Open the datasource to operate on.

    ds = ogr.Open( infile, update = 0 )

    poly_layer = ds.GetLayerByName( 'Polygon' )

    #############################################################################
    #	Create output file for the composed polygons.

    nad83 = osr.SpatialReference()
    nad83.SetFromUserInput('NAD83')

    shp_driver = ogr.GetDriverByName( 'ESRI Shapefile' )
    shp_driver.DeleteDataSource( outfile )

    shp_ds = shp_driver.CreateDataSource( outfile )

    shp_layer = shp_ds.CreateLayer( 'out', geom_type = ogr.wkbPolygon,
                                    srs = nad83 )

    src_defn = poly_layer.GetLayerDefn()
    poly_field_count = src_defn.GetFieldCount()

    for fld_index in range(poly_field_count):
        src_fd = src_defn.GetFieldDefn( fld_index )

        fd = ogr.FieldDefn( src_fd.GetName(), src_fd.GetType() )
        fd.SetWidth( src_fd.GetWidth() )
        fd.SetPrecision( src_fd.GetPrecision() )
        shp_layer.CreateField( fd )

    #############################################################################
    # Read all features in the line layer, holding just the geometry in a hash
    # for fast lookup by TLID.

    line_layer = ds.GetLayerByName( 'CompleteChain' )
    line_count = 0

    modules_hash = {}

    feat = line_layer.GetNextFeature()
    geom_id_field = feat.GetFieldIndex( 'TLID' )
    tile_ref_field = feat.GetFieldIndex( 'MODULE' )
    while feat is not None:
        geom_id = feat.GetField( geom_id_field )
        tile_ref = feat.GetField( tile_ref_field )

        try:
            module = modules_hash[tile_ref]
        except:
            module = Module()
            modules_hash[tile_ref] = module

        module.lines[geom_id] = feat.GetGeometryRef().Clone()
        line_count = line_count + 1

        feat.Destroy()

        feat = line_layer.GetNextFeature()

    print('Got %d lines in %d modules.' % (line_count,len(modules_hash)))

    #############################################################################
    # Read all polygon/chain links and build a hash keyed by POLY_ID listing
    # the chains (by TLID) attached to it.

    link_layer = ds.GetLayerByName( 'PolyChainLink' )

    feat = link_layer.GetNextFeature()
    geom_id_field = feat.GetFieldIndex( 'TLID' )
    tile_ref_field = feat.GetFieldIndex( 'MODULE' )
    lpoly_field = feat.GetFieldIndex( 'POLYIDL' )
    rpoly_field = feat.GetFieldIndex( 'POLYIDR' )

    link_count = 0

    while feat is not None:
        module = modules_hash[feat.GetField( tile_ref_field )]

        tlid = feat.GetField( geom_id_field )

        lpoly_id = feat.GetField( lpoly_field )
        rpoly_id = feat.GetField( rpoly_field )


        if lpoly_id == rpoly_id:
            feat.Destroy()
            feat = link_layer.GetNextFeature()
            continue

        try:
            module.poly_line_links[lpoly_id].append( tlid )
        except:
            module.poly_line_links[lpoly_id] = [ tlid ]

        try:
            module.poly_line_links[rpoly_id].append( tlid )
        except:
            module.poly_line_links[rpoly_id] = [ tlid ]

        link_count = link_count + 1

        feat.Destroy()

        feat = link_layer.GetNextFeature()

    print('Processed %d links.' % link_count)

    #############################################################################
    # Process all polygon features.

    feat = poly_layer.GetNextFeature()
    tile_ref_field = feat.GetFieldIndex( 'MODULE' )
    polyid_field = feat.GetFieldIndex( 'POLYID' )

    poly_count = 0
    degenerate_count = 0

    while feat is not None:
        module = modules_hash[feat.GetField( tile_ref_field )]
        polyid = feat.GetField( polyid_field )

        tlid_list = module.poly_line_links[polyid]

        link_coll = ogr.Geometry( type = ogr.wkbGeometryCollection )
        for tlid in tlid_list:
            geom = module.lines[tlid]
            link_coll.AddGeometry( geom )

        try:
            poly = ogr.BuildPolygonFromEdges( link_coll )

            if poly.GetGeometryRef(0).GetPointCount() < 4:
                degenerate_count = degenerate_count + 1
                poly.Destroy()
                feat.Destroy()
                feat = poly_layer.GetNextFeature()
                continue

            #print poly.ExportToWkt()
            #feat.SetGeometryDirectly( poly )

            feat2 = ogr.Feature(feature_def=shp_layer.GetLayerDefn())

            for fld_index in range(poly_field_count):
                feat2.SetField( fld_index, feat.GetField( fld_index ) )

            feat2.SetGeometryDirectly( poly )

            shp_layer.CreateFeature( feat2 )
            feat2.Destroy()

            poly_count = poly_count + 1
        except:
            print('BuildPolygonFromEdges failed.')

        feat.Destroy()

        feat = poly_layer.GetNextFeature()

    if degenerate_count:
        print('Discarded %d degenerate polygons.' % degenerate_count)

    print('Built %d polygons.' % poly_count)

    #############################################################################
    # Cleanup

    shp_ds.Destroy()
    ds.Destroy()


# Modified from original at
# https://svn.osgeo.org/gdal/tags/1.4.3/gdal/pymod/samples/tigerpoly.py
from gdal import osr, ogr
from warnings import warn
import geopandas as gpd


def tiger_to_tract(infile):
    class Module:
        def __init__(self):
            self.lines = {}
            self.poly_line_links = {}

    outfile = 'poly.shp'

    # Open the datasource to operate on.

    ds = ogr.Open(infile, update=0)
    poly_layer = ds.GetLayerByName('Polygon')

    # Create output file for the composed polygons.

    nad83 = osr.SpatialReference()
    nad83.SetFromUserInput('NAD83')

    shp_driver = ogr.GetDriverByName('ESRI Shapefile')
    shp_driver.DeleteDataSource(outfile)

    shp_ds = shp_driver.CreateDataSource(outfile)

    shp_layer = shp_ds.CreateLayer('out', geom_type=ogr.wkbPolygon, srs=nad83)

    src_defn = poly_layer.GetLayerDefn()
    poly_field_count = src_defn.GetFieldCount()

    for fld_index in range(poly_field_count):
        src_fd = src_defn.GetFieldDefn(fld_index)

        fd = ogr.FieldDefn(src_fd.GetName(), src_fd.GetType())
        fd.SetWidth(src_fd.GetWidth())
        fd.SetPrecision(src_fd.GetPrecision())
        shp_layer.CreateField(fd)

    # Read all features in the line layer, holding just the geometry in a hash
    # for fast lookup by TLID.

    line_layer = ds.GetLayerByName('CompleteChain')
    line_count = 0

    modules_hash = {}

    feat = line_layer.GetNextFeature()
    geom_id_field = feat.GetFieldIndex('TLID')
    tile_ref_field = feat.GetFieldIndex('MODULE')
    while feat is not None:
        geom_id = feat.GetField(geom_id_field)
        tile_ref = feat.GetField(tile_ref_field)

        try:
            module = modules_hash[tile_ref]
        except:
            module = Module()
            modules_hash[tile_ref] = module

        module.lines[geom_id] = feat.GetGeometryRef().Clone()
        line_count = line_count + 1

        feat.Destroy()

        feat = line_layer.GetNextFeature()

    # Read all polygon/chain links and build a hash keyed by POLY_ID listing
    # the chains (by TLID) attached to it.

    link_layer = ds.GetLayerByName('PolyChainLink')

    feat = link_layer.GetNextFeature()
    geom_id_field = feat.GetFieldIndex('TLID')
    tile_ref_field = feat.GetFieldIndex('MODULE')
    lpoly_field = feat.GetFieldIndex('POLYIDL')
    rpoly_field = feat.GetFieldIndex('POLYIDR')

    link_count = 0

    while feat is not None:
        module = modules_hash[feat.GetField(tile_ref_field)]

        tlid = feat.GetField(geom_id_field)

        lpoly_id = feat.GetField(lpoly_field)
        rpoly_id = feat.GetField(rpoly_field)

        if lpoly_id == rpoly_id:
            feat.Destroy()
            feat = link_layer.GetNextFeature()
            continue

        try:
            module.poly_line_links[lpoly_id].append(tlid)
        except:
            module.poly_line_links[lpoly_id] = [tlid]

        try:
            module.poly_line_links[rpoly_id].append(tlid)
        except:
            module.poly_line_links[rpoly_id] = [tlid]

        link_count = link_count + 1

        feat.Destroy()

        feat = link_layer.GetNextFeature()

    # Process all polygon features.

    feat = poly_layer.GetNextFeature()
    tile_ref_field = feat.GetFieldIndex('MODULE')
    polyid_field = feat.GetFieldIndex('POLYID')

    poly_count = 0
    degenerate_count = 0

    while feat is not None:
        module = modules_hash[feat.GetField(tile_ref_field)]
        polyid = feat.GetField(polyid_field)

        tlid_list = module.poly_line_links[polyid]

        link_coll = ogr.Geometry(type=ogr.wkbGeometryCollection)
        for tlid in tlid_list:
            geom = module.lines[tlid]
            link_coll.AddGeometry(geom)

        try:
            poly = ogr.BuildPolygonFromEdges(link_coll)

            if poly.GetGeometryRef(0).GetPointCount() < 4:
                degenerate_count = degenerate_count + 1
                poly.Destroy()
                feat.Destroy()
                feat = poly_layer.GetNextFeature()
                continue

            # print poly.ExportToWkt()
            # feat.SetGeometryDirectly( poly )

            feat2 = ogr.Feature(feature_def=shp_layer.GetLayerDefn())

            for fld_index in range(poly_field_count):
                feat2.SetField(fld_index, feat.GetField(fld_index))

            feat2.SetGeometryDirectly(poly)

            shp_layer.CreateFeature(feat2)
            feat2.Destroy()

            poly_count = poly_count + 1
        except:
            warn('BuildPolygonFromEdges failed.')

        feat.Destroy()

        feat = poly_layer.GetNextFeature()

    if degenerate_count:
        warn('Discarded %d degenerate polygons.' % degenerate_count)

    print('Built %d polygons.' % poly_count)

    # Cleanup

    shp_ds.Destroy()
    ds.Destroy()

    # build a fully-qualified fips code and dissolve on it to create tract geographies
    gdf = gpd.read_file(outfile)

    if "CTBNA90" in gdf.columns:

        gdf = gdf.rename(columns={"CTBNA90": 'TRACT'})

    gdf['STATE'] = gdf['STATE'].astype(str).str.rjust(2, "0")

    gdf['COUNTY'] = gdf['COUNTY'].astype(str).str.rjust(3, "0")

    gdf['TRACT'] = gdf['TRACT'].astype(str).str.rjust(4, "0")

    gdf['fips'] = gdf.STATE + gdf.COUNTY + gdf.TRACT + '00'

    gdf.to_file(outfile)

    gdf = gdf.dropna(subset=['fips'])
    gdf = gdf.dissolve(by='fips')

    gdf.reset_index(inplace=True)

    gdf.to_file(outfile)

    return gdf
#!/usr/bin/env python
###############################################################################
# $Id$
#
# Project:  OGR Python samples
# Purpose:  Assemble TIGER Polygons.
# Author:   Frank Warmerdam, warmerdam@pobox.com
#
###############################################################################
# Copyright (c) 2003, Frank Warmerdam <warmerdam@pobox.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
# OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.
###############################################################################
#
#  $Log$
#  Revision 1.5  2005/07/29 04:49:46  fwarmerdam
#  Set SRS on generated file.
#  http://bugzilla.remotesensing.org/show_bug.cgi?id=644
#
#  Revision 1.4  2004/10/30 20:54:42  fwarmerdam
#  Applied patch from Schuyler Erle (bug 646) to discard dangles and
#  degenerate rings.
#
#  Revision 1.3  2003/07/11 14:52:13  warmerda
#  Added logic to replicate all source polygon fields onto output file.
#
#  Revision 1.2  2003/07/11 14:31:17  warmerda
#  Use provided input filename.
#
#  Revision 1.1  2003/03/03 05:17:06  warmerda
#  New
#
#

import osr
import ogr
import string
import sys


#############################################################################
def tiger_to_tract(infile):
    class Module:

        def __init__( self ):
            self.lines = {}
            self.poly_line_links = {}
#############################################################################
# Argument processing.

    outfile = 'poly.shp'

    #############################################################################
    # Open the datasource to operate on.

    ds = ogr.Open( infile, update = 0 )

    poly_layer = ds.GetLayerByName( 'Polygon' )

    #############################################################################
    #	Create output file for the composed polygons.

    nad83 = osr.SpatialReference()
    nad83.SetFromUserInput('NAD83')

    shp_driver = ogr.GetDriverByName( 'ESRI Shapefile' )
    shp_driver.DeleteDataSource( outfile )

    shp_ds = shp_driver.CreateDataSource( outfile )

    shp_layer = shp_ds.CreateLayer( 'out', geom_type = ogr.wkbPolygon,
                                    srs = nad83 )

    src_defn = poly_layer.GetLayerDefn()
    poly_field_count = src_defn.GetFieldCount()

    for fld_index in range(poly_field_count):
        src_fd = src_defn.GetFieldDefn( fld_index )

        fd = ogr.FieldDefn( src_fd.GetName(), src_fd.GetType() )
        fd.SetWidth( src_fd.GetWidth() )
        fd.SetPrecision( src_fd.GetPrecision() )
        shp_layer.CreateField( fd )

    #############################################################################
    # Read all features in the line layer, holding just the geometry in a hash
    # for fast lookup by TLID.

    line_layer = ds.GetLayerByName( 'CompleteChain' )
    line_count = 0

    modules_hash = {}

    feat = line_layer.GetNextFeature()
    geom_id_field = feat.GetFieldIndex( 'TLID' )
    tile_ref_field = feat.GetFieldIndex( 'MODULE' )
    while feat is not None:
        geom_id = feat.GetField( geom_id_field )
        tile_ref = feat.GetField( tile_ref_field )

        try:
            module = modules_hash[tile_ref]
        except:
            module = Module()
            modules_hash[tile_ref] = module

        module.lines[geom_id] = feat.GetGeometryRef().Clone()
        line_count = line_count + 1

        feat.Destroy()

        feat = line_layer.GetNextFeature()

    print('Got %d lines in %d modules.' % (line_count,len(modules_hash)))

    #############################################################################
    # Read all polygon/chain links and build a hash keyed by POLY_ID listing
    # the chains (by TLID) attached to it.

    link_layer = ds.GetLayerByName( 'PolyChainLink' )

    feat = link_layer.GetNextFeature()
    geom_id_field = feat.GetFieldIndex( 'TLID' )
    tile_ref_field = feat.GetFieldIndex( 'MODULE' )
    lpoly_field = feat.GetFieldIndex( 'POLYIDL' )
    rpoly_field = feat.GetFieldIndex( 'POLYIDR' )

    link_count = 0

    while feat is not None:
        module = modules_hash[feat.GetField( tile_ref_field )]

        tlid = feat.GetField( geom_id_field )

        lpoly_id = feat.GetField( lpoly_field )
        rpoly_id = feat.GetField( rpoly_field )


        if lpoly_id == rpoly_id:
            feat.Destroy()
            feat = link_layer.GetNextFeature()
            continue

        try:
            module.poly_line_links[lpoly_id].append( tlid )
        except:
            module.poly_line_links[lpoly_id] = [ tlid ]

        try:
            module.poly_line_links[rpoly_id].append( tlid )
        except:
            module.poly_line_links[rpoly_id] = [ tlid ]

        link_count = link_count + 1

        feat.Destroy()

        feat = link_layer.GetNextFeature()

    print('Processed %d links.' % link_count)

    #############################################################################
    # Process all polygon features.

    feat = poly_layer.GetNextFeature()
    tile_ref_field = feat.GetFieldIndex( 'MODULE' )
    polyid_field = feat.GetFieldIndex( 'POLYID' )

    poly_count = 0
    degenerate_count = 0

    while feat is not None:
        module = modules_hash[feat.GetField( tile_ref_field )]
        polyid = feat.GetField( polyid_field )

        tlid_list = module.poly_line_links[polyid]

        link_coll = ogr.Geometry( type = ogr.wkbGeometryCollection )
        for tlid in tlid_list:
            geom = module.lines[tlid]
            link_coll.AddGeometry( geom )

        try:
            poly = ogr.BuildPolygonFromEdges( link_coll )

            if poly.GetGeometryRef(0).GetPointCount() < 4:
                degenerate_count = degenerate_count + 1
                poly.Destroy()
                feat.Destroy()
                feat = poly_layer.GetNextFeature()
                continue

            #print poly.ExportToWkt()
            #feat.SetGeometryDirectly( poly )

            feat2 = ogr.Feature(feature_def=shp_layer.GetLayerDefn())

            for fld_index in range(poly_field_count):
                feat2.SetField( fld_index, feat.GetField( fld_index ) )

            feat2.SetGeometryDirectly( poly )

            shp_layer.CreateFeature( feat2 )
            feat2.Destroy()

            poly_count = poly_count + 1
        except:
            print('BuildPolygonFromEdges failed.')

        feat.Destroy()

        feat = poly_layer.GetNextFeature()

    if degenerate_count:
        print('Discarded %d degenerate polygons.' % degenerate_count)

    print('Built %d polygons.' % poly_count)

    #############################################################################
    # Cleanup

    shp_ds.Destroy()
    ds.Destroy()


# Modified from original at
# https://svn.osgeo.org/gdal/tags/1.4.3/gdal/pymod/samples/tigerpoly.py
from gdal import osr, ogr
from warnings import warn
import geopandas as gpd


def tiger_to_tract(infile):
    class Module:
        def __init__(self):
            self.lines = {}
            self.poly_line_links = {}

    outfile = 'poly.shp'

    # Open the datasource to operate on.

    ds = ogr.Open(infile, update=0)
    poly_layer = ds.GetLayerByName('Polygon')

    # Create output file for the composed polygons.

    nad83 = osr.SpatialReference()
    nad83.SetFromUserInput('NAD83')

    shp_driver = ogr.GetDriverByName('ESRI Shapefile')
    shp_driver.DeleteDataSource(outfile)

    shp_ds = shp_driver.CreateDataSource(outfile)

    shp_layer = shp_ds.CreateLayer('out', geom_type=ogr.wkbPolygon, srs=nad83)

    src_defn = poly_layer.GetLayerDefn()
    poly_field_count = src_defn.GetFieldCount()

    for fld_index in range(poly_field_count):
        src_fd = src_defn.GetFieldDefn(fld_index)

        fd = ogr.FieldDefn(src_fd.GetName(), src_fd.GetType())
        fd.SetWidth(src_fd.GetWidth())
        fd.SetPrecision(src_fd.GetPrecision())
        shp_layer.CreateField(fd)

    # Read all features in the line layer, holding just the geometry in a hash
    # for fast lookup by TLID.

    line_layer = ds.GetLayerByName('CompleteChain')
    line_count = 0

    modules_hash = {}

    feat = line_layer.GetNextFeature()
    geom_id_field = feat.GetFieldIndex('TLID')
    tile_ref_field = feat.GetFieldIndex('MODULE')
    while feat is not None:
        geom_id = feat.GetField(geom_id_field)
        tile_ref = feat.GetField(tile_ref_field)

        try:
            module = modules_hash[tile_ref]
        except:
            module = Module()
            modules_hash[tile_ref] = module

        module.lines[geom_id] = feat.GetGeometryRef().Clone()
        line_count = line_count + 1

        feat.Destroy()

        feat = line_layer.GetNextFeature()

    # Read all polygon/chain links and build a hash keyed by POLY_ID listing
    # the chains (by TLID) attached to it.

    link_layer = ds.GetLayerByName('PolyChainLink')

    feat = link_layer.GetNextFeature()
    geom_id_field = feat.GetFieldIndex('TLID')
    tile_ref_field = feat.GetFieldIndex('MODULE')
    lpoly_field = feat.GetFieldIndex('POLYIDL')
    rpoly_field = feat.GetFieldIndex('POLYIDR')

    link_count = 0

    while feat is not None:
        module = modules_hash[feat.GetField(tile_ref_field)]

        tlid = feat.GetField(geom_id_field)

        lpoly_id = feat.GetField(lpoly_field)
        rpoly_id = feat.GetField(rpoly_field)

        if lpoly_id == rpoly_id:
            feat.Destroy()
            feat = link_layer.GetNextFeature()
            continue

        try:
            module.poly_line_links[lpoly_id].append(tlid)
        except:
            module.poly_line_links[lpoly_id] = [tlid]

        try:
            module.poly_line_links[rpoly_id].append(tlid)
        except:
            module.poly_line_links[rpoly_id] = [tlid]

        link_count = link_count + 1

        feat.Destroy()

        feat = link_layer.GetNextFeature()

    # Process all polygon features.

    feat = poly_layer.GetNextFeature()
    tile_ref_field = feat.GetFieldIndex('MODULE')
    polyid_field = feat.GetFieldIndex('POLYID')

    poly_count = 0
    degenerate_count = 0

    while feat is not None:
        module = modules_hash[feat.GetField(tile_ref_field)]
        polyid = feat.GetField(polyid_field)

        tlid_list = module.poly_line_links[polyid]

        link_coll = ogr.Geometry(type=ogr.wkbGeometryCollection)
        for tlid in tlid_list:
            geom = module.lines[tlid]
            link_coll.AddGeometry(geom)

        try:
            poly = ogr.BuildPolygonFromEdges(link_coll)

            if poly.GetGeometryRef(0).GetPointCount() < 4:
                degenerate_count = degenerate_count + 1
                poly.Destroy()
                feat.Destroy()
                feat = poly_layer.GetNextFeature()
                continue

            # print poly.ExportToWkt()
            # feat.SetGeometryDirectly( poly )

            feat2 = ogr.Feature(feature_def=shp_layer.GetLayerDefn())

            for fld_index in range(poly_field_count):
                feat2.SetField(fld_index, feat.GetField(fld_index))

            feat2.SetGeometryDirectly(poly)

            shp_layer.CreateFeature(feat2)
            feat2.Destroy()

            poly_count = poly_count + 1
        except:
            warn('BuildPolygonFromEdges failed.')

        feat.Destroy()

        feat = poly_layer.GetNextFeature()

    if degenerate_count:
        warn('Discarded %d degenerate polygons.' % degenerate_count)

    print('Built %d polygons.' % poly_count)

    # Cleanup

    shp_ds.Destroy()
    ds.Destroy()

    # build a fully-qualified fips code and dissolve on it to create tract geographies
    gdf = gpd.read_file(outfile)

    if "CTBNA90" in gdf.columns:

        gdf = gdf.rename(columns={"CTBNA90": 'TRACT'})

    gdf['STATE'] = gdf['STATE'].astype(str).str.rjust(2, "0")

    gdf['COUNTY'] = gdf['COUNTY'].astype(str).str.rjust(3, "0")

    gdf['TRACT'] = gdf['TRACT'].astype(str).str.rjust(4, "0")

    gdf['fips'] = gdf.STATE + gdf.COUNTY + gdf.TRACT + '00'

    gdf.to_file(outfile)

    gdf = gdf.dropna(subset=['fips'])
    gdf = gdf.dissolve(by='fips')

    gdf.reset_index(inplace=True)

    gdf.to_file(outfile)

    return gdf

