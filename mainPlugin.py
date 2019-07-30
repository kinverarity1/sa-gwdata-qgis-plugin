import os


from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *

from qgis.core import *


from pathlib import Path
import os
import struct
import subprocess
import sys
import traceback
import uuid

from qgis.core import Qgis, QgsMessageLog

import matplotlib.pyplot as plt


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
        self.actions = []
        self.path = Path(os.path.dirname(os.path.abspath(__file__)))
        self.wells_layer = None
        self.wc_session = sa_gwdata.WaterConnectSession()

    def initGui(self):
        load_wells_in_map_extent = Action(
            self,
            QIcon(str(self.path / "icon.png")),
            "Load wells in map extent",
            self.iface.mainWindow(),
        )
        load_wells_in_map_extent.action.setShortcut("F8")
        load_wells_in_map_extent.set_task(FindMapCanvasWellsTask, (self,), {})
        self.iface.addPluginToMenu(
            "SA &Groundwater Data", load_wells_in_map_extent.action
        )
        self.actions.append(load_wells_in_map_extent)

        wl_for_selected = Action(
            self,
            QIcon(str(self.path / "icon.png")),
            "Get water levels for selected wells",
            self.iface.mainWindow(),
        )
        wl_for_selected.action.setShortcut("F9")
        wl_for_selected.set_task(
            ParamTimeSeriesPlotTask,
            (self,),
            {
                "bulk_download_service": "GetWaterLevelDownload",
                "datecol": "obs_date",
                "paramcol": "rswl",
                "ylabel": "RSWL (m AHD)",
            },
        )
        self.iface.addPluginToMenu("SA &Groundwater Data", wl_for_selected.action)
        self.actions.append(wl_for_selected)

        tds_for_selected = Action(
            self,
            QIcon(str(self.path / "icon.png")),
            "Get salinity samples for selected wells",
            self.iface.mainWindow(),
        )
        tds_for_selected.action.setShortcut("F10")
        tds_for_selected.set_task(
            ParamTimeSeriesPlotTask,
            (self,),
            {
                "bulk_download_service": "GetSalinityDownload",
                "datecol": "Collected_date",
                "paramcol": "TDS",
                "ylabel": "TDS (mg/L)",
            },
        )
        self.iface.addPluginToMenu("SA &Groundwater Data", tds_for_selected.action)
        self.actions.append(tds_for_selected)

        # self.iface.mapCanvas().renderComplete.connect(self.renderTest)

    def unload(self):
        for action in self.actions:
            self.iface.removePluginMenu("SA &Groundwater Data", action.action)
        # self.iface.removeToolBarIcon(self.action)
        # self.iface.mapCanvas().renderComplete.disconnect(self.renderTest)

    def run_task(self, task):
        tag = str(id(task))
        globals()[tag] = task
        QgsApplication.taskManager().addTask(globals()[tag])

    def load_wells_in_map_extent(self):
        self.run_task()

    def renderTest(self, painter):
        # use painter for drawing to map canvas
        # print("SAGwDataPlugin: renderTest called!")
        pass


class Action:
    def __init__(self, parent, *args, **kwargs):
        self.parent = parent
        self.action = QAction(*args, **kwargs)

    def set_task(self, task_cls, task_args, task_kwargs):
        self.slot = lambda: self.parent.run_task(task_cls(*task_args, **task_kwargs))
        self.action.triggered.connect(self.slot)


def subdivide_rect(xs, ys, split="x"):
    xs = sorted(xs)
    ys = sorted(ys)
    xd = ((xs[1] - xs[0]) / 2) + xs[0]
    yd = ((ys[1] - ys[0]) / 2) + ys[0]
    if split == "y":
        return [(xs, [ys[0], yd]), (xs, [yd, ys[1]])]
    elif split == "x":
        return [([xs[0], xd], ys), ([xd, xs[1]], ys)]


class Task(QgsTask):
    def __init__(self, plugin):
        self.exception = None
        self.plugin = plugin
        super().__init__(uuid.uuid4().hex, QgsTask.CanCancel)

    def log(self, msg, level=Qgis.Info):
        QgsMessageLog.logMessage(msg, self.__class__.__name__, level)

    def get_waterconnect_session(self):
        try:
            self.wc_session = sa_gwdata.WaterConnectSession()
        except requests.exceptions.ConnectionError:
            time.sleep(2)
            try:
                self.wc_session = sa_gwdata.WaterConnectSession()
            except:
                self.exception = Exception(traceback.format_exc().splitlines()[-1])
                return False
        return True

    def finished_success(self):
        pass

    def finished(self, result):
        if result:
            self.log('Task "{}" completed.'.format(self.description))
            self.finished_success()
        else:
            if self.exception is None:
                self.log(
                    'Task "{name}" not successful but without '
                    "exception (probably the task was manually "
                    "canceled by the user)".format(name=self.description()),
                    level=Qgis.Warning,
                )
            else:
                self.log(
                    'Task "{name}" Exception: {exception}'.format(
                        name=self.description(), exception=self.exception
                    ),
                    level=Qgis.Critical,
                )
                raise self.exception

    def cancel(self):
        self.log('Task "{name}" was canceled'.format(name=self.description()))
        super().cancel()


def apply_well_id(row, cols=["Obs_No", "Unit_No"]):
    for col in cols:
        if row[col]:
            return row[col]
    return ""


class ParamTimeSeriesPlotTask(Task):
    def __init__(self, plugin, bulk_download_service, datecol, paramcol, ylabel):
        super().__init__(plugin)
        layer = plugin.iface.activeLayer()
        fields = layer.fields().names()
        self.dh_nos = []
        for feature in layer.selectedFeatures():
            vals = dict(zip(fields, feature.attributes()))
            self.dh_nos.append(vals["dh_no"])
        self.bulk_download_service = bulk_download_service
        self.datecol = datecol
        self.paramcol = paramcol
        self.ylabel = ylabel

    def run(self):
        if not self.get_waterconnect_session():
            return False
        try:
            df = self.wc_session.bulk_download(
                self.bulk_download_service, {"DHNOs": self.dh_nos}
            )
            self.log(str(df))
            df[self.datecol] = pd.to_datetime(df[self.datecol], format="%d/%m/%Y")
            df["well_id"] = df.apply(apply_well_id, axis="columns")
        except:
            self.exception = Exception(traceback.format_exc())
            return False
        self.df = df
        return True

    def finished_success(self):
        self.log(
            "Found {} values from {}".format(len(self.df), self.bulk_download_service)
        )
        self.log(str([x for x in self.df.columns]))
        fig = plt.figure()
        ax = fig.add_subplot(111)
        for well_id, wdf in self.df.groupby("well_id"):
            wdf = wdf.sort_values(self.datecol)
            ax.plot(
                wdf[self.datecol],
                wdf[self.paramcol],
                label=well_id,
                lw=1,
                marker=".",
                ms=5,
            )
        ax.set_ylabel(self.ylabel)
        ax.legend(loc="best", frameon=False, fontsize="small")
        fig.tight_layout()
        fig.show()


class FindMapCanvasWellsTask(Task):
    def __init__(self, plugin):
        super().__init__(plugin)

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
        self.lats = lats
        self.lons = lons

    def run(self):
        self.log('Started task "{}"'.format(self.description()))

        def get_wells(rects):
            all_wells = []
            for lats, lons in rects:
                self.log("Fetching wells from: lats={}, lons={}".format(lats, lons))
                wells = self.wc_session.find_wells_in_lat_lon(lats=lats, lons=lons)
                self.log("Found {} wells".format(len(wells)))
                if len(wells) == 10000:
                    self.log("Subdividing rectangle and starting again")
                    wells = get_wells(subdivide_rect(lats, lons))
                all_wells += wells
            return sa_gwdata.Wells(all_wells)

        if not self.get_waterconnect_session():
            return False

        try:
            lats = self.lats
            lons = self.lons
            wells = get_wells([[lats, lons]])
            wells_df = wells.df()
            for col in WELL_COLUMNS:
                if not col in wells_df:
                    wells_df[col] = ""
            for datecol in WELL_DATE_COLUMNS:
                wells_df[datecol] = pd.to_datetime(
                    wells_df[datecol], format=r"%Y-%m-%d"
                )
                wells_df[datecol + "_year"] = wells_df[datecol].dt.year
            self.log(str([x for x in wells_df.columns]))
            wells_df["well_id"] = wells_df.apply(
                lambda x: apply_well_id(x, ("obs_no", "unit_no")), axis="columns"
            )
        except:
            self.exception = Exception(traceback.format_exc())
            return False
        self.wells_df = wells_df
        return True

    def finished_success(self):
        self.log("{} wells found".format(len(self.wells_df)))
        self.plugin.wells_layer = df_to_vector_layer(
            self.wells_df, vlayer=self.plugin.wells_layer
        )
        if not self.plugin.wells_layer in self.plugin.iface.mapCanvas().layers():
            QgsProject.instance().addMapLayer(self.plugin.wells_layer)


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
