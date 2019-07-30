import os


from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *

from qgis.core import *


import os
import struct
import subprocess
import sys
import traceback

from qgis.core import Qgis, QgsMessageLog


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


def get_python_exe():
    # In QGIS this is the QGIS executable, rather than Python
    path = sys.executable
    path = os.path.join(
        os.path.dirname(os.path.dirname(path)), "apps", "Python37", "python.exe"
    )
    assert os.path.isfile(path)
    print("Detected Python interpreter: " + path)
    return path


def get_python_bitness():
    if struct.calcsize("P") == 8:
        bitness = "amd64"
    else:
        bitness = "win32"
    print("Detected Python bitness: " + bitness)
    return bitness


def get_python_version():
    version_str = sys.version
    ver = version_str[0] + version_str[2]
    print("Detected Python version: " + ver)
    return ver


def install_bundled_packages_with_pip(packages):
    py_bit = get_python_bitness()
    py_ver = get_python_version()
    get_local = lambda f: os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "dependencies", f
    ).format(py_ver=py_ver, py_bit=py_bit)
    for package in packages:
        install_with_pip(get_local(package))


def install_with_pip(package):
    py_exe = get_python_exe()
    command = " ".join(['"' + py_exe + '"', "-m", "pip", "install", "--user", package])
    print("Running command: " + command)
    output = subprocess.check_output(command, stderr=subprocess.STDOUT)
    print("Output:\n" + output.decode("ascii"))


try:
    import requests
except:
    install_with_pip("requests")

try:
    import sa_gwdata
except:
    install_with_pip("https://github.com/kinverarity1/python-sa-gwdata/zipball/master")

try:
    import pandas as pd
except:
    install_bundled_packages_with_pip(
        ["pandas-0.25.0-cp{py_ver}-cp{py_ver}m-win_{py_bit}.whl"]
    )


class SAGwDataPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.wells_layer = None
        self.wc_session = sa_gwdata.WaterConnectSession()

    def initGui(self):
        self.action = QAction(
            QIcon(os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.png")),
            "Load wells in map extent",
            self.iface.mainWindow(),
        )
        self.action.setObjectName("testAction")
        self.action.triggered.connect(self.load_wells_in_map_extent)
        self.iface.addPluginToMenu("SA &Groundwater Data", self.action)
        self.iface.mapCanvas().renderComplete.connect(self.renderTest)

    def unload(self):
        self.iface.removePluginMenu("SA &Groundwater Data", self.action)
        self.iface.removeToolBarIcon(self.action)
        self.iface.mapCanvas().renderComplete.disconnect(self.renderTest)

    def load_wells_in_map_extent(self):
        task = FindMapCanvasWellsTask(self)
        tag = str(id(task))
        globals()[tag] = task
        QgsApplication.taskManager().addTask(globals()[tag])

    def renderTest(self, painter):
        # use painter for drawing to map canvas
        # print("SAGwDataPlugin: renderTest called!")
        pass


class FindMapCanvasWellsTask(QgsTask):

    MESSAGE_CATEGORY = "FindMapCanvasWellsTask"

    def __init__(self, plugin):
        self.exception = None
        self.plugin = plugin

        canvas = self.plugin.iface.mapCanvas()
        extent = canvas.extent()
        extent_crs = canvas.mapSettings().destinationCrs()
        wgs84 = QgsCoordinateReferenceSystem(4326)
        transform = QgsCoordinateTransform(
            extent_crs, wgs84, canvas.mapSettings().transformContext()
        )
        wgs84_extent = transform.transform(extent)
        lats = [wgs84_extent.yMinimum(), wgs84_extent.yMaximum()]
        lons = [wgs84_extent.xMinimum(), wgs84_extent.xMaximum()]
        description = "Find wells in lats={}, lons={}".format(tuple(lats), tuple(lons))
        super().__init__(description, QgsTask.CanCancel)
        self.lats = lats
        self.lons = lons

    def run(self):
        """Here you implement your heavy lifting.
        Should periodically test for isCanceled() to gracefully
        abort.
        This method MUST return True or False.
        Raising exceptions will crash QGIS, so we handle them
        internally and raise them in self.finished
        """
        QgsMessageLog.logMessage(
            'Started task "{}"'.format(self.description()),
            self.MESSAGE_CATEGORY,
            Qgis.Info,
        )
        try:
            wc_session = sa_gwdata.WaterConnectSession()
            wells = wc_session.find_wells_in_lat_lon(lats=self.lats, lons=self.lons)
            wells_df = wells.df()
            for col in WELL_COLUMNS:
                if not col in wells_df:
                    wells_df[col] = ""
        except:
            self.exception = Exception(traceback.format_exc())
            return False
        self.wells_df = wells_df
        return True

    def finished(self, result):
        if result:
            QgsMessageLog.logMessage(
                'Task "{}" completed. {} wells found.'.format(
                    self.description, len(self.wells_df)
                ),
                self.MESSAGE_CATEGORY,
                Qgis.Info,
            )
            self.plugin.wells_layer = df_to_vector_layer(
                self.wells_df, vlayer=self.plugin.wells_layer
            )
            if not self.plugin.wells_layer in self.plugin.iface.mapCanvas().layers():
                QgsProject.instance().addMapLayer(self.plugin.wells_layer)
        else:
            if self.exception is None:
                QgsMessageLog.logMessage(
                    'Task "{name}" not successful but without '
                    "exception (probably the task was manually "
                    "canceled by the user)".format(name=self.description()),
                    self.MESSAGE_CATEGORY,
                    Qgis.Warning,
                )
            else:
                QgsMessageLog.logMessage(
                    'Task "{name}" Exception: {exception}'.format(
                        name=self.description(), exception=self.exception
                    ),
                    self.MESSAGE_CATEGORY,
                    Qgis.Critical,
                )
                raise self.exception

    def cancel(self):
        QgsMessageLog.logMessage(
            'Task "{name}" was canceled'.format(name=self.description()),
            self.MESSAGE_CATEGORY,
            Qgis.Info,
        )
        super().cancel()


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
            if dtype.startswith("int"):
                typ = QVariant.Int
            elif dtype.startswith("float"):
                typ = QVariant.Double
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
