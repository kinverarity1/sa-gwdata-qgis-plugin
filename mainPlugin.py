from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *


class SAGwDataPlugin:
    def __init__(self, iface):
        # save reference to the QGIS interface
        self.iface = iface

    def initGui(self):
        # create action that will start plugin configuration
        self.action = QAction(
            QIcon(":/plugins/sa-gwdata-qgis/icon.png"),
            "SA Groundwater Data plugin",
            self.iface.mainWindow(),
        )
        self.action.setObjectName("testAction")
        self.action.setWhatsThis("Configuration for SA Groundwater Data plugin")
        self.action.setStatusTip("This is status tip")
        self.action.triggered.connect(self.run)

        # add toolbar button and menu item
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("SA &Groundwater Data", self.action)

        # connect to signal renderComplete which is emitted when canvas
        # rendering is done
        self.iface.mapCanvas().renderComplete.connect(self.renderTest)

    def unload(self):
        # remove the plugin menu item and icon
        self.iface.removePluginMenu("SA &Groundwater Data", self.action)
        self.iface.removeToolBarIcon(self.action)

        # disconnect form signal of the canvas
        self.iface.mapCanvas().renderComplete.disconnect(self.renderTest)

    def run(self):
        # create and show a configuration dialog or something similar
        print("SAGwDataPlugin: run called!")

    def renderTest(self, painter):
        # use painter for drawing to map canvas
        print("SAGwDataPlugin: renderTest called!")

