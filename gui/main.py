import asyncio
import configparser
import os
import sys
import threading

import platformdirs

from view import RidenPSUView
from model_control import RidenPSUModelControl

# Could create this programatically, but that way doesn't support comments....so smash it in by hand
DEFAULT_CONFIG = \
"""[MQTT]
; MQTT server hostname or IP address and port (typically 1883 for unsecure connections and 8883 for TLS secured connections)
hostname = mqtt
port = 1883

; Optional client ID to provide to server (helps identify the source / purpose of the connection)
client_id = rd60xx_gui

; Optional username and password if required by the server
;username = user
;password = pass

; Optional certificate authority filename for server certificate validation
;ca_cert = ca.crt

; Optional client certificate and associated key if the server requires client certificates
;client_cert = client.crt
;client_key = client.key

; Optionally allow "insecure" TLS connections.
; Allowing for example a connection to continue if the server's certificate common name doesn't match its hostname or IP address
;insecure = yes

[GENERAL]
; MQTT topic name to use (should match bridge server application)
mqtt_base_topic = riden_psu

; Delay before reconnecting if MQTT connection lost
mqtt_reconnect_delay_secs = 5

; Update period
;update_period = 0.25
"""

def main():
    """Entrypoint"""

    # Retrieve config directory (creating if neccessary)
    config_dir = platformdirs.user_config_dir("RD60xxMQTTRemoteControl", "QuantulumLtd", ensure_exists=True)

    # Add config filename
    config_path = os.path.join(config_dir, "config.ini")

    # Write default config
    no_config_file = not os.path.exists(config_path)
    if no_config_file:
        try:
            with open(config_path, "w") as f:
                f.write(DEFAULT_CONFIG)
        except:
            # Ignore failure to write file....likely permissions or dinosaur related
            pass

    # Load config file
    config = configparser.ConfigParser()
    config.read(config_path)

    # Extract config - MQTT
    hostname = config.get(section="MQTT", option="hostname", fallback=None)
    port = config.getint(section="MQTT", option="port", fallback=1883)
    client_id = config.get(section="MQTT", option="client_id", fallback=None)
    username = config.get(section="MQTT", option="username", fallback=None)
    password = config.get(section="MQTT", option="password", fallback=None)
    ca_cert = config.get(section="MQTT", option="ca_cert", fallback=None)
    client_cert = config.get(section="MQTT", option="client_cert", fallback=None)
    client_key = config.get(section="MQTT", option="client_key", fallback=None)
    insecure = config.getboolean(section="MQTT", option="insecure", fallback=False)

    # Extract config - general
    mqtt_base_topic = config.get(section="GENERAL", option="mqtt_base_topic", fallback="riden_psu")
    mqtt_reconnect_delay_secs = config.getfloat(section="GENERAL", option="mqtt_reconnect_delay_secs", fallback=5)
    mqtt_probe_delay_secs = config.getfloat(section="GENERAL", option="mqtt_probe_delay_secs", fallback=1)
    update_period = config.getfloat(section="GENERAL", option="update_period", fallback=0.25)

    # Change to the "Selector" event loop if platform is Windows as required by aiomqtt
    if sys.platform.lower() == "win32" or os.name.lower() == "nt":
        from asyncio import set_event_loop_policy, WindowsSelectorEventLoopPolicy
        set_event_loop_policy(WindowsSelectorEventLoopPolicy())

    # Create new event loop and assign as asyncio loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Start asyncio loop in background thread
    threading.Thread(target=asyncio_loop_thread, args=(loop, ), daemon=True).start()

    # Construct model
    model_ctrl = RidenPSUModelControl(hostname, port,
                                      client_id=client_id,
                                      username=username,
                                      password=password,
                                      ca_cert=ca_cert,
                                      client_cert=client_cert,
                                      client_key=client_key,
                                      insecure=insecure,
                                      mqtt_base_topic=mqtt_base_topic,
                                      mqtt_reconnect_delay_secs=mqtt_reconnect_delay_secs,
                                      mqtt_probe_delay_secs=mqtt_probe_delay_secs,
                                      update_period=update_period)

    # Construct view
    view = RidenPSUView(no_config_file, config_path)

    # Link view and model/controller
    model_ctrl.set_view(view)
    view.set_model_controller(model_ctrl)

    # Run model and view
    model_ctrl.run()
    view.run()
    model_ctrl.stop()

def asyncio_loop_thread(loop: asyncio.AbstractEventLoop) -> None:
    """Run event loop"""

    # Run loop until stopped
    loop.run_forever()

if __name__ == "__main__":
    main()
