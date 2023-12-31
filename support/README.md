# Support

This directory contains various supporting files.

## Decode

The `decode` directory contains a quick and dirty decoder for the ESP-Touch protocol. It operates using UDP packet lengths however, rather than 802.11 frame lengths.

## Registers

The original modbus register definitions for the RD60xx family were retrieved from: [Baldanos python module](https://github.com/Baldanos/rd6006/blob/master/registers.md).

## Packaging

The GUI has been packaged for Windows, Linux and macOS using the python library pyinstaller, as follows:

```
python3 -m venv venv
source venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
python3 -m pip install pyinstaller pillow
pyinstaller --clean --onefile --noconsole --icon ruideng.png --name RD60xxMQTTRemoteControl main.py
```
