import os
import struct
import subprocess
import sys


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
    import seaborn
except:
    install_with_pip("seaborn")

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
