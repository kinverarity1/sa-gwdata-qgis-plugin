def classFactory(iface):
    from .mainPlugin import SAGwDataPlugin

    return SAGwDataPlugin(iface)


__version__ = "0.1.0"
