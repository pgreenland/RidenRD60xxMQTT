# Bridge

## Introduction

This directory contains a python application which acts as a bridge between one or more Wi-Fi connected power supply units (PSU) and an MQTT broker.

It connects to a nominated MQTT server while listening on TCP port 8080. Waiting for PSUs to connect. Connected PSUs are advertised via MQTT where they may be queried or controlled via JSON formatted MQTT messages.

## Launching

The bridge application should be installed on a machine with a static IP, for example a Raspberry Pi or small always-on server.

An example configuration file `config.ini` is included which should be customised before launching.

The `[MQTT]` section contains the connection details for the MQTT server, the configuration of which is outside the scope of this readme. Assuming a server such as Apache Mosquitto is available, the configuration options provided should allow for most variations of secure / insecure and authenticated / non-authenticated connections.

#### Virtual Environment

Once confgured the application may be launched locally, within a virtual environment as follows:

```
python3 -m venv venv
source venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
python3 main.py
```

#### Docker Image

A docker image has been pushed to DockerHub:

```
docker run --rm -it -p 8080:8080 -v ./config.ini:/app/config.ini pgreenland/riden_psu_mqtt_bridge
```

#### Docker Building

Alternatively a `Dockerfile` is provided, such that a container may be build and launched as follows:

```
docker build -t riden_psu_mqtt_bridge .
docker run --rm -it -p 8080:8080 -v ./config.ini:/app/config.ini riden_psu_mqtt_bridge
```

When started an output similar the following should be seen:

```
[2023-12-30 18:58:10,444] [RD60xxToMQTT] [INFO] MQTT task running
[2023-12-30 18:58:10,447] [RD60xxToMQTT] [INFO] PSU task running
[2023-12-30 18:58:10,456] [RD60xxToMQTT] [INFO] MQTT connected!
```

Indicating that the application has connected to the MQTT server and is waiting for power supplies to connect.

Upon connection messages similar to the following should be seen:

```
[2023-12-30 18:59:29,643] [RD60xxToMQTT] [INFO] PSU connected (192.168.1.143:17668)
[2023-12-30 18:59:32,938] [RD60xxToMQTT] [INFO] PSU 192.168.1.143:17668's identity is 60062_23024, it's name is 'Unnamed'
```

Power supplies may be named by editing the `[PSUS]` section of the config file. The example shown above may be named `My PSU` by appending the following line to the section:

```
60062_23024 = My PSU
```

PSU names will be transmitted along side their identity (60062_23024 in the example above) when being advertised via MQTT. Allowing client applications to differentiate between them in a more use friendly manner.

## MQTT Messages

The application listens for and transmits messages on an MQTT topic which may be set in the `config.ini` file via the `mqtt_base_topic` parameter in the `[GENERAL]` section.

The default base topic used is `riden_psu`, all messages to/from the application will appear on this topic.

All messages are formatted using JSON.

## BASE_TOPIC/psu/list/get

The application subscribes to messages published to this topic by clients. The payload isn't currently used.

When the application receives a message on this topic it will publish a PSU list message as described below.

## BASE_TOPIC/psu/list

Messages are published to this topic by the application when power supplies connect or the list is requested as described above.

Messages include a list of currently connected power supplies, each list entry contains the following fields:


| Field     | Type    | Description                                                                                         |   |   |   |
|-----------|---------|-----------------------------------------------------------------------------------------------------|---|---|---|
| identity  | string  | Unit identity, combination of its model and serial number. Used in topics to communicate with unit. |   |   |   |
| name      | string  | Name associated with unit, from config file.                                                        |   |   |   |
| model     | integer | Unit model number, consisting of model and hardware revision.                                       |   |   |   |
| serial_no | integer | Unit serial number.                                                                                 |   |   |   |

For example:

```
[
  {
    "identity": "60062_23024",
    "name": "Unnamed",
    "model": 60062,
    "serial_no": 23024
  }
]
```

## BASE_TOPIC/psu/IDENTITY/state/get

The application subscribes to messages published to this topic by clients. IDENTITY is the PSU identity to query.

Messages may include the following optional fields:

| Field  | Type  | Description                                                                                                                                 |   |   |   |
|--------|-------|---------------------------------------------------------------------------------------------------------------------------------------------|---|---|---|
| query  | bool  | If true, query the unit and publish the result. If false, do not query the unit but publish a state message indicating whether its online.  |   |   |   |

For example:

```
{
  "query": True
}
```

## BASE_TOPIC/psu/IDENTITY/state

Messages are published to this topic by the application when new state information is received from the PSU.

Either the application can be set to periodically query the unit, or will query the unit when requested via a message.

Messages will typically include the following fields:

| Field               | Type    | Description                                                                                                                                                                                                        |   |   |   |
|---------------------|---------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---|---|---|
| connected           | bool    | True if the PSU is connected, false otherwise.                                                                                                                                                                     |   |   |   |
| period              | float   | Automatic query period (secs). If zero querying is stopped, if > 0 the daemon will query the unit at this rate and publish a state message.                                                                        |   |   |   |
| model               | integer | Unit model number, consisting of model and hardware revision.                                                                                                                                                      |   |   |   |
| serial_no           | integer | Unit serial number.                                                                                                                                                                                                |   |   |   |
| firmware_version    | string  | Firmware version. e.g. "1.41".                                                                                                                                                                                     |   |   |   |
| temp_c              | float   | Internal temperature sensor reading degrees C.                                                                                                                                                                     |   |   |   |
| temp_f              | float   | Internal temperature sensor reading degrees F.                                                                                                                                                                     |   |   |   |
| current_range       | integer | RD6012P only, current range selection (0 = 6A, 1 = 12A)                                                                                                                                                                   |   |   |   |
| output_volage_set   | float   | Set output voltage.                                                                                                                                                                                                |   |   |   |
| output_current_set  | float   | Set output current.                                                                                                                                                                                                |   |   |   |
| ovp                 | float   | M0 over-voltage protection limit.                                                                                                                                                                                  |   |   |   |
| ocp                 | float   | M0 over-current protection limit.                                                                                                                                                                                  |   |   |   |
| output_voltage_disp | float   | Displayed output voltage.                                                                                                                                                                                          |   |   |   |
| output_current_disp | float   | Displayed output current.                                                                                                                                                                                          |   |   |   |
| output_power_disp   | float   | Displayed output power.                                                                                                                                                                                            |   |   |   |
| input_voltage       | float   | Supply input voltage.                                                                                                                                                                                              |   |   |   |
| protection_status   | string  | Output protection status. One of "normal", output is functioning normally. "ovp", output was disabled having gone over the over-voltage limit. "ocp", output was disabled having gone over the over-current limit. |   |   |   |
| output_mode         | string  | Output operating mode. One of "cv", output is in constant voltage mode. Or "cc", output is in constant current mode.                                                                                               |   |   |   |
| output_enable       | bool    | True if output is enabled, false otherwise.                                                                                                                                                                        |   |   |   |
| battery_mode        | bool    | True if the unit is in battery charging mode, false otherwise.                                                                                                                                                     |   |   |   |
| battery_voltage     | float   | Voltage measured on battery charging connector.                                                                                                                                                                    |   |   |   |
| ext_temp_c          | float   | External temperature sensor reading in degrees C.                                                                                                                                                                  |   |   |   |
| ext_temp_f          | float   | External temperature sensor reading in degrees F.                                                                                                                                                                  |   |   |   |
| batt_ah             | float   | Battery charger / output number of amp-hours delivered.                                                                                                                                                            |   |   |   |
| batt_wh             | float   | Battery charger / output number of watt-hours delivered.                                                                                                                                                           |   |   |   |
| presets             | array   | Array of preset objects, M1 -> M9.                                                                                                                                                                                           |   |   |   |

Each entry in the preset array contains the following fields:

| Field | Type  | Description                           |
|-------|-------|---------------------------------------|
| v     | float | Preset voltage.                       |
| c     | float | Preset current.                       |
| ovp   | float | Preset over-voltage protection limit. |
| ocp   | float | Preset over-current protection limit. |

For example:

```
{
  "connected": true,
  "period": 0,
  "model": 60062,
  "serial_no": 23024,
  "firmware_version": "1.41",
  "temp_c": 29,
  "temp_f": 84,
  "current_range": 0,
  "output_voltage_set": 12,
  "output_current_set": 1,
  "ovp": 62,
  "ocp": 6.2,
  "output_voltage_disp": 0,
  "output_current_disp": 0,
  "output_power_disp": 0,
  "input_voltage": 61.06,
  "protection_status": "normal",
  "output_mode": "cv",
  "output_enable": false,
  "battery_mode": false,
  "battery_voltage": 0,
  "ext_temp_c": 31,
  "ext_temp_f": 87,
  "batt_ah": 0,
  "batt_wh": 0,
  "presets": [
    {
      "v": 12,
      "c": 1,
      "ovp": 62,
      "ocp": 6.2
    },
    {
      "v": 5,
      "c": 6.1,
      "ovp": 62,
      "ocp": 6.2
    },
    {
      "v": 5,
      "c": 6.1,
      "ovp": 62,
      "ocp": 6.2
    },
    {
      "v": 5,
      "c": 6.1,
      "ovp": 62,
      "ocp": 6.2
    },
    {
      "v": 5,
      "c": 6.1,
      "ovp": 62,
      "ocp": 6.2
    },
    {
      "v": 5,
      "c": 6.1,
      "ovp": 62,
      "ocp": 6.2
    },
    {
      "v": 5,
      "c": 6.1,
      "ovp": 62,
      "ocp": 6.2
    },
    {
      "v": 5,
      "c": 6.1,
      "ovp": 62,
      "ocp": 6.2
    },
    {
      "v": 5,
      "c": 6.1,
      "ovp": 62,
      "ocp": 6.2
    }
  ]
}
```

If a PSU is queried in response to a get request via MQTT, a message containing only the connected and period fields may be published.

For example:

```
{
  "connected": true,
  "period": 0
}
```

## BASE_TOPIC/psu/IDENTITY/state/set

The application subscribes to messages published to this topic by clients. IDENTITY is the PSU identity to manage.

Messages may include the following optional fields:

| Field              | Type  | Description                                                                                                                                 |
|--------------------|-------|---------------------------------------------------------------------------------------------------------------------------------------------|
| period             | float | Automatic query period (secs). If zero querying is stopped, if > 0 the daemon will query the unit at this rate and publish a state message. |
| preset_index       | float | Preset voltage.                                                                                                                             |
| output_voltage_set | float | Preset current.                                                                                                                             |
| output_current_set | float | Preset over-voltage protection limit.                                                                                                       |
| ovp                | float | M0 over-voltage protection limit.                                                                                                           |
| ocp                | float | M0 over-current protection limit.                                                                                                           |
| output_enable      | bool  | Output status. True to enable, false to disable.                                                                                            |
| output_toggle      | bool  | Output toggle request. True to toggle output status, false to not modify output status.                                                     |

Only fields which are present will be modified, therefore to enable the output the following example message may be sent:

```
{
  "output_enable" : true
}
```
