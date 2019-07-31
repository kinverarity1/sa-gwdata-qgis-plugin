from pathlib import Path
import os
import struct
import subprocess
import sys
import traceback
import uuid

import matplotlib.pyplot as plt

from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *
from qgis.core import *

from .install_dependencies import *

import requests
import pandas as pd
import seaborn as sns
import sa_gwdata

from .utils import *


class Task(QgsTask):
    """Convenience parent class for tasks."""

    def __init__(self, plugin):
        self.exception = None
        self.plugin = plugin
        super().__init__(uuid.uuid4().hex, QgsTask.CanCancel)

    def log(self, msg, level=Qgis.Info):
        """Write a message to the QGIS Log Messages Panel.

        Args:
            msg (str): log message
            level (enum): Qgis.Warning, Qgis.Critical, Qgis.Info, etc.

        """
        QgsMessageLog.logMessage(msg, self.__class__.__name__, level)

    def get_waterconnect_session(self):
        """Obtain a session connection to WaterConnect Groundwater Data.

        Session is stored as ``self.wc_session``.

        Returns: True or False.

        If False, the task should be cancelled by you from ``self.run()``.

        """
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
        """This method should be implemented by child classes. It is 
        called from the main thread in the case that the task's execution
        was successfull."""
        pass

    def finished(self, result):
        """Called from the main thread with the result of ``self.run()``.
        
        Args:
            result (bool): the return value of ``self.run()``.
            
        """
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
        """Called when the task was cancelled."""
        self.log('Task "{name}" was canceled'.format(name=self.description()))
        super().cancel()


class FindMapCanvasWellsTask(Task):
    '''Load wells in the extent of the map canvas, and update
    the plugin's designated "wells" layer with the results.

    Args:
        plugin (SAGwData object): the plugin class.

    '''
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
        '''Run the task in the background.

        Downloads wells from the current extent from WaterConnect
        using python-sa-gwdata.

        '''
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
                lambda x: apply_well_id(x, ("obs_no.id", "unit_no.hyphen")),
                axis="columns",
            )
            for col in wells_df.columns:
                dtype = wells_df[col].dtype.name
                if dtype[0].upper() in ("O", "S"):
                    wells_df.loc[pd.isnull(wells_df[col]), col] = ""
        except:
            self.exception = Exception(traceback.format_exc())
            return False
        self.wells_df = wells_df
        return True

    def finished_success(self):
        '''On completion, convert the downloaded pandas DataFrame
        to the plugin's "wells" QgsVectorLayer.

        '''
        self.log("{} wells found".format(len(self.wells_df)))

        wells_layer_existed = self.plugin.wells_layer != None
        self.plugin.wells_layer = df_to_vector_layer(
            self.wells_df, vlayer=self.plugin.wells_layer, name="sa_gwdata wells"
        )
        if not wells_layer_existed:
            self.plugin.wells_layer.destroyed.connect(self.plugin.wells_layer_removed)
        if not self.plugin.wells_layer in self.plugin.iface.mapCanvas().layers():
            self.plugin.wells_layer.loadNamedStyle(
                os.path.join(
                    os.path.dirname(os.path.abspath(__file__)), "well_id_labels.qml"
                )
            )
            QgsProject.instance().addMapLayer(self.plugin.wells_layer)


class ParamTimeSeriesPlotTask(Task):
    '''Abstract task class for downloading a time series of parameter
    data from Groundwater Data and making a chart with a temporary
    vector layer highlighting the wells charted.

    Args:
        plugin (SAGwDataPlugin object): the plugin object
        bulk_download_service (str): name of API endpoint on Groundwater Data
            e.g. "GetWaterLevelDownload"
        datecol (str): name of column with observation dates.
        paramcol (str): name of column with data
        ylabel (str): y-axis label for chart

    '''
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
        self.all_wells_df = self.plugin.wells_layer_df()

    def run(self):
        '''Download data as DataFrame as background task.'''
        if not self.get_waterconnect_session():
            return False
        try:
            df = self.wc_session.bulk_download(
                self.bulk_download_service, {"DHNOs": self.dh_nos}
            )
            self.log("Param Plot task: columns = {}".format(str(df.columns.values)))
            df[self.datecol] = pd.to_datetime(df[self.datecol], format=r"%d/%m/%Y")
            df = df.dropna(subset=[self.datecol, self.paramcol], how="any")
            df["well_id"] = df.apply(apply_well_id, axis="columns")
            self.df = df
            well_ids = list(df["well_id"].unique())
            self.log("well_ids 265. : {}".format(str(well_ids)))
            self.well_ids = sorted([x for x in well_ids if isinstance(x, str)])
            self.log("self.well_ids 267. : {}".format(str(self.well_ids)))
            if len(self.df) == 0:
                self.log("No data points were found!!")
                return False
            self.colours = sns.color_palette("bright", len(self.well_ids))
        except:
            self.exception = Exception(traceback.format_exc())
            return False

        return True

    def finished_success(self):
        '''When finished, create a temporary vector layer for wells, with each point
        colour-coded as they are on the chart itself.'''
        dh_nos = self.df.DHNO.unique()
        df = self.all_wells_df[self.all_wells_df.dh_no.isin(dh_nos)]
        layer = df_to_vector_layer(
            df, name="Fig {:.0f} {}".format(self.fignum, self.paramcol)
        )

        # A colour category for each feature.
        categories = []
        for i, well_id in enumerate(self.well_ids):
            symbol = QgsSymbol.defaultSymbol(layer.geometryType())
            self.log("well_id {} id(symbol) {}".format(well_id, id(symbol)))
            colour = self.colours[i]
            colour_256 = [x * 255 for x in colour]
            qcolor = QColor(*colour_256)
            self.log(
                "well_id {} colour {} colour_256 {} qcolor {}".format(
                    well_id, colour, colour_256, qcolor
                )
            )
            for symbol_layer in symbol.symbolLayers():
                symbol_layer.setFillColor(qcolor)
            label = well_id
            aq_mon = self.all_wells_df[lambda x: x.well_id == well_id].aq_mon.iloc[0]
            if not pd.isnull(aq_mon):
                label += " {}".format(aq_mon)
            category = QgsRendererCategory(well_id, symbol, label)
            categories.append(category)
        renderer = QgsCategorizedSymbolRenderer("well_id", categories)
        layer.setRenderer(renderer)
        QgsProject.instance().addMapLayer(layer)
        layer.triggerRepaint()
        self.plugin.iface.layerTreeView().refreshLayerSymbology(layer.id())
        self.plugin.iface.setActiveLayer(self.plugin.wells_layer)


class WaterLevelPlotTask(ParamTimeSeriesPlotTask):
    '''Create water level chart.

    Args:
        paramcol (str): either "rswl" or "swl"
        ylabel (str): y-axis label

    '''
    def __init__(self, plugin, paramcol, ylabel):
        super().__init__(
            plugin,
            bulk_download_service="GetWaterLevelDownload",
            datecol="obs_date",
            paramcol=paramcol,
            ylabel=ylabel,
        )

    def finished_success(self):
        '''Draw the chart figure and make it appear.'''
        self.log(
            "Found {} values from {}".format(len(self.df), self.bulk_download_service)
        )
        self.log(str([x for x in self.df.columns]))
        fig = plt.figure()
        ax = fig.add_subplot(111)
        for i, well_id in enumerate(self.well_ids):
            wdf = self.df[self.df["well_id"] == well_id]
            label = well_id
            aq_mon = self.all_wells_df[lambda x: x.well_id == well_id].aq_mon.iloc[0]
            if not pd.isnull(aq_mon):
                label += " {}".format(aq_mon)
            if len(wdf):
                wdf = wdf.sort_values(self.datecol)
                ax.plot(
                    wdf[self.datecol],
                    wdf[self.paramcol],
                    label=label,
                    color=self.colours[i],
                    lw=1,
                    marker=".",
                    ms=5,
                )
        ax.set_ylabel(self.ylabel)
        if self.paramcol == "swl":
            ax.invert_yaxis()
        ax.legend(loc="best", frameon=False, fontsize="small")
        fig.tight_layout()
        self.fignum = fig.number
        super().finished_success()
        fig.show()


class SalinityPlotTask(ParamTimeSeriesPlotTask):
    '''Create salinity chart.

    Args:
        paramcol (str): either "TDS" or "EC"
        ylabel (str): y-axis label

    '''
    def __init__(self, plugin, paramcol, ylabel):
        super().__init__(
            plugin,
            bulk_download_service="GetSalinityDownload",
            datecol="Collected_date",
            paramcol=paramcol,
            ylabel=ylabel,
        )

    def finished_success(self):
        '''Draw the chart figure and make it appear. Separate lines
        will appear for bailed and pumped samples. Other data are shown
        as points only.
        
        '''
        self.log(
            "Found {} values from {}".format(len(self.df), self.bulk_download_service)
        )
        self.log(str([x for x in self.df.columns]))
        fig = plt.figure()
        ax = fig.add_subplot(111)

        self.df.loc[self.df.extract_method.isnull(), "extract_method"] = "UKN"
        for i, well_id in enumerate(self.well_ids):
            wdf = self.df[self.df["well_id"] == well_id]
            if len(wdf):
                wdf = wdf.sort_values(["extract_method", self.datecol])
                for j, (extract_method, edf) in enumerate(
                    wdf.groupby("extract_method")
                ):
                    edf = edf.sort_values(self.datecol)
                    ax.plot(
                        edf[self.datecol],
                        edf[self.paramcol],
                        color=self.colours[i],
                        label="",
                        **EXTRACT_METHOD_KWS[extract_method]
                    )
                label = well_id
                aq_mon = self.all_wells_df[lambda x: x.well_id == well_id].aq_mon.iloc[
                    0
                ]
                if not pd.isnull(aq_mon):
                    label += " {}".format(aq_mon)
                ax.plot([], [], color=self.colours[i], lw=3, label=label)
        for extract_method in self.df["extract_method"].unique():
            ax.plot(
                [],
                [],
                color="k",
                **EXTRACT_METHOD_KWS[extract_method],
                label=extract_method
            )
        ax.set_ylabel(self.ylabel)
        ax.legend(loc="best", frameon=False, fontsize="small")
        fig.tight_layout()
        self.fignum = fig.number
        super().finished_success()
        fig.show()
