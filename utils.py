from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *
from qgis.core import *

WELL_COLUMNS = [
    "dh_no",
    "id",
    "title",
    "name",
    "unit_no.map",
    "unit_no.seq",
    "unit_no.hyphen",
    "unit_no.long",
    "unit_no.long_int",
    "unit_no.wilma",
    "unit_no.hydstra",
    "obs_no.plan",
    "obs_no.seq",
    "obs_no.id",
    "obs_no.egis",
    "lat",
    "lon",
    "max_depth",
    "drill_date",
    "swl",
    "yield",
    "tds",
    "class",
    "nrm",
    "logdrill",
    "litholog",
    "chem",
    "water",
    "sal",
    "obswell",
    "stratlog",
    "hstratlog",
    "latest_swl_date",
    "latest_sal_date",
    "latest_yield_date",
    "latest_open_depth",
    "latest_open_date",
    "stat_desc",
    "purp_desc",
    "aq_mon",
    "permit_no",
    "pwa",
    "obsnetwork",
    "swlstatus",
    "salstatus",
    "replaceunitnum",
]

WELL_DATE_COLUMNS = [
    "drill_date",
    "latest_swl_date",
    "latest_sal_date",
    "latest_open_date",
    "latest_yield_date",
]

EXTRACT_METHOD_KWS = {
    "BAIL": {"lw": 0.5, "marker": "v", "mfc": "none", "mew": 1},
    "PUMP": {"lw": 1, "marker": ".", "ms": 8},
    "FLOW": {"marker": "o", "ms": 8},
    "UKN": {"ls": "none", "marker": "s"},
    "AIRL": {"ls": "none", "marker": "o"},
    "WMLL": {"ls": "none", "marker": "d"},
}


def subdivide_rect(xs, ys, split="x"):
    """Subdivide a rectangle into two either along
    the x or y axis.

    Args:
        xs (list): the min and max x coordinates
        ys (list): the min and max y coordinates
        split (str): either "x" or "y", the axis to split on.

    """
    xs = sorted(xs)
    ys = sorted(ys)
    xd = ((xs[1] - xs[0]) / 2) + xs[0]
    yd = ((ys[1] - ys[0]) / 2) + ys[0]
    if split == "y":
        return [(xs, [ys[0], yd]), (xs, [yd, ys[1]])]
    elif split == "x":
        return [([xs[0], xd], ys), ([xd, xs[1]], ys)]


def apply_well_id(row, cols=["Obs_No", "Unit_No"]):
    """Used with pandas.DataFrame.apply to create a "well_id"
    column which contains the obs number if it exists, and if
    not the unit number.

    """
    for col in cols:
        if row[col]:
            return row[col]
    return ""


def df_to_vector_layer(df, vlayer=None, name="wells", xcol="lon", ycol="lat"):
    """Convert pandas.DataFrame to vector layer."""
    if vlayer is None:
        create_vlayer = True
    else:
        create_vlayer = False

    if create_vlayer:
        vlayer = QgsVectorLayer("Point?crs=epsg:4326", name, "memory")

    pr = vlayer.dataProvider()
    vlayer.startEditing()

    if create_vlayer:
        fields = []
        for col in df:
            series = df[col]
            dtype = series.dtype.name
            print((col, dtype))
            if dtype.startswith("int"):
                typ = QVariant.Int
            elif dtype.startswith("float"):
                typ = QVariant.Double
            elif col in WELL_DATE_COLUMNS:
                typ = QVariant.DateTime
            else:
                typ = QVariant.String
            field = QgsField(col, typ)
            fields.append(field)
        pr.addAttributes(fields)
        vlayer.updateFields()

    dh_nos = []
    if not create_vlayer:
        for feature in vlayer.getFeatures():
            dh_nos.append(feature["dh_no"])

    names = vlayer.fields().names()

    features = []
    for _, row in df[~df.dh_no.isin(dh_nos)].iterrows():
        row = row.to_dict()
        fet = QgsFeature()
        fet.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(row[xcol], row[ycol])))
        values = []
        for col in names:
            try:
                value = row[col]
            except KeyError:
                value = ""
            values.append(value)
        fet.setAttributes(values)
        features.append(fet)
    pr.addFeatures(features)
    vlayer.commitChanges()
    return vlayer
