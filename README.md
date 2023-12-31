# RuiDeng Riden RD60xx Remote Control via MQTT

This repository contains python applications and related scripts. Together they enable remote control (via MQTT) of the RuiDeng Riden RD60xx family of bench top power supplies. Provided the unit is fitted with Riden's optional Wi-Fi adapter.

## Bridge

The `bridge` directory contains a python application which acts as a bridge between one or more Wi-Fi connected power supply units (PSU) and an MQTT broker.

The RuiDeng Riden power supples speak Modbus via UART. The optional onboard Wi-Fi adapter effectively acts as a Wi-Fi to UART bridge.

The implementation used by the PSU is slightly odd in a few ways.

Firstly although there's a TCP/IP standard for Modbus, due to the UART briding behavior of the Wi-Fi daughterboard, the remote application uses UART framing rather than TCP framing for Modbus commands and responses.

Secondly the PSU acts as a TCP client, connecting to a TCP server on a remote machine. In a typical Modbus over TCP implementation, the PSU would act as the TCP server and the controlling application would act as a TCP client.

In somes ways however this makes for quite a neat solution as the bridge application simply waits for connections from one (or potentially more) PSUs, making each of them available via MQTT.

See `README.md` within the bridge directory for more information.

## GUI

I'd originally planned to get as far as the bridge application and stop....with the plan of squirting control messages straight into the MQTT broker.

However I got a bit carried away and though it may be "fun" (a relative term in this case) to develop a basic GUI mimmocking the RD60xx PSU screen itself.

The `gui` directory contains a python application based on PySimpleGUI providing a simple user interface.

Conecting to an MQTT broker it displays data arriving from the PSU (via the bridge). While allowing for common parameters (output voltage / current, preset selection and output enable) to be modified.

See `README.md` within the gui directory for more information.

## Provisioning

The `provisioning` directory contains a python script, which implements the provisioning protocol used by the power supply.

This allows a factory fresh (or a power supply which has previously been provisioned by RuiDeng's mobile apps) to be reconfigured to communicate with a machine running the PSU to MQTT bridge application.

Configuration should be possible using any Wi-Fi equipped machine, which is connected to a 2.4Ghz Wi-Fi network.

See `README.md` within the provisioning directory for more information.
