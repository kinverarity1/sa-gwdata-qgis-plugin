from pathlib import Path
import os
import struct
import subprocess
import sys
import traceback
import uuid
import webbrowser

import matplotlib.pyplot as plt

from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *
from qgis.core import *

# Install all required dependencies into QGIS' Python environment.
from .install_dependencies import *
from .plugin_tasks import *
from .utils import *


class SAGwDataPlugin:
    """Main QGIS plugin class."""

    def __init__(self, iface):
        self.iface = iface
        self.actions = []
        self.path = Path(os.path.dirname(os.path.abspath(__file__)))
        self.wells_layer = None
        for layer in self.iface.mapCanvas().layers():
            if layer.isValid():
                if layer.name() == "sa_gwdata wells":
                    self.wells_layer = layer
                    self.wells_layer.destroyed.connect(self.wells_layer_removed)

        self.wc_session = sa_gwdata.WaterConnectSession()

    def wells_layer_removed(self):
        self.wells_layer = None

    def initGui(self):
        """Method required by QGIS to initialise plugin."""

        # "Load wells in map extent" menu item.
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

        # "Get water levels for selected wells" menu item.
        wl_for_selected = Action(
            self,
            QIcon(str(self.path / "icon.png")),
            "Chart water levels for selected wells",
            self.iface.mainWindow(),
        )
        wl_for_selected.action.setShortcut("F9")
        wl_for_selected.set_task(
            WaterLevelPlotTask, (self,), {"paramcol": "rswl", "ylabel": "RSWL (m AHD)"}
        )
        self.iface.addPluginToMenu("SA &Groundwater Data", wl_for_selected.action)
        self.actions.append(wl_for_selected)

        # "Get salinity sample data for selected wells" menu item
        tds_for_selected = Action(
            self,
            QIcon(str(self.path / "icon.png")),
            "Chart bulk salinity sample data for selected wells",
            self.iface.mainWindow(),
        )
        tds_for_selected.action.setShortcut("F10")
        tds_for_selected.set_task(
            SalinityPlotTask, (self,), {"paramcol": "TDS", "ylabel": "TDS (mg/L)"}
        )
        self.iface.addPluginToMenu("SA &Groundwater Data", tds_for_selected.action)
        self.actions.append(tds_for_selected)

        load_wells_in_browser = Action(
            self,
            QIcon(str(self.path / "icon.png")),
            "Load selected wells in Groundwater Data",
            self.iface.mainWindow(),
        )
        load_wells_in_browser.action.setShortcut("F12")
        load_wells_in_browser.action.triggered.connect(self.load_wells_in_browser)
        self.iface.addPluginToMenu("SA &Groundwater Data", load_wells_in_browser.action)
        self.actions.append(load_wells_in_browser)

    def load_wells_in_browser(self):
        for feature in self.iface.activeLayer().selectedFeatures():
            dh_no = int(feature["dh_no"])
            webbrowser.open(
                "https://www.waterconnect.sa.gov.au/Systems/GD/Pages/Details.aspx?DHNO={}".format(
                    dh_no
                )
            )

    def wells_layer_df(self):
        names = self.wells_layer.fields().names()
        rows = []
        for feature in self.wells_layer.getFeatures():
            rows.append(dict(zip(names, feature.attributes())))
        return pd.DataFrame(rows)

    def unload(self):
        """Uninstall plugin. Remove all UI interface elements and disconnect slots
        from signals."""
        for action in self.actions:
            self.iface.removePluginMenu("SA &Groundwater Data", action.action)

    def run_task(self, task):
        """Run a QgsTask as a global variable (doesn't run if it is local).

        Args:
            task (QgsTask): a task to start running.

        """
        tag = str(id(task))
        globals()[tag] = task
        QgsApplication.taskManager().addTask(globals()[tag])


class Action:
    """Simple wrapper around a plugin action where the action
    corresponds to a thread-safe task (QgsTask).

    Args:
        parent (plugin object): the parent SAGwDataPlugin
            object. It must have a ``run_task`` method, which
            accepts a QgsTask object.
        *args, **kwargs: used to create the QAction, which is
            stored as the attribute ``action``.

    """

    def __init__(self, parent, *args, **kwargs):
        self.parent = parent
        self.action = QAction(*args, **kwargs)

    def set_task(self, task_cls, task_args, task_kwargs):
        """Set the task which should be created and run when the 
        action is triggered.

        Args:
            task_cls (class inherited from QgsTask): the task class
            task_args (iterable): arguments for task_cls
            task_kwargs (dict): keyword arguments for task_cls

        When the action is triggered, an instance of task_cls will be 
        created with the supplied arguments, and then run.

        """
        self.slot = lambda: self.parent.run_task(task_cls(*task_args, **task_kwargs))
        self.action.triggered.connect(self.slot)

