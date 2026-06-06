# GUI

## Introduction

This directory contains a python application which implements a simple GUI attempting to mimic the LCD display on the power supply unit (PSU).

It connects to a nominated MQTT server, communicating with PSUs via the bridge application.

## Launching

The application may be launched locally, within a virtual environment as follows:

Linux / macOS:

```
python3 -m venv venv
source venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
python3 main.py
```

Windows:

```
python3 -m venv venv
venv\Scripts\activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
python3 main.py
```

The GUI will be rendered by FreeSimpleGUI which under the hood uses Python's standard interface to Tcl/Tk tkinter.
This isn't included by default with every python installation. If you see an error such as `ModuleNotFoundError: No module named 'tkinter'` when launching, it may need to be installed separately.

The following is summarised from: https://pytutorial.com/how-to-install-tkinter-in-python/

Windows:

Windows builds of python will typically include Tkinter, however it can be installed via pip if not:

```
python3 -m pip install tk
```

macOS:

If python was installed via Homebrew, Tkinter may be installed separately with:

```
brew install python-tk
```

Linux:

For Debian/Ubuntu, Tkinter can typically be installed with:

```
sudo apt-get install python3-tk
```

For Fedora:

```
sudo dnf install python3-tkinter
```

On first run the application will request broker details be configured, opening an example configuration in the system's default text editor.

## Packaging

The application may be packaged, with its dependencies to make it feel a little more native.

Within the virtual environment created above:

```
python3 -m pip install pyinstaller pillow
pyinstaller --onefile --windowed --icon ruideng.png main.py
```

Which will provide a single file python application in the `dist` directory.
