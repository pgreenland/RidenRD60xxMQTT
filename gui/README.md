# GUI

## Introduction

This directory contains a python application which implements a simple GUI attempting to mimmock the LCD display on the power supply unit (PSU).

It connects to a nominated MQTT server, communicating with PSUs via the bridge application.

## Launching

The application may be launched locally, within a virtual environment as follows:

```
python3 -m venv venv
source venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
python3 main.py
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
