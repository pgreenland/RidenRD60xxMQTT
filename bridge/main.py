import asyncio
import configparser
import logging
import os
import sys

from rd60xx_to_mqtt import RD60xxToMQTT

def main():
    """Entrypoint"""

    # Init logging
    logging.basicConfig(stream=sys.stdout,
                        level=logging.INFO,
                        #format='[%(asctime)s] [%(filename)s:%(funcName)s:%(lineno)d] [%(name)s] [%(levelname)s] %(message)s'
                        format='[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s'
                       )


    # Retrieve config file path
    config_path = os.path.join(os.path.dirname(__file__), "config.ini")

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
    log_level = config.get(section="GENERAL", option="log_level", fallback="info")
    mqtt_base_topic = config.get(section="GENERAL", option="mqtt_base_topic", fallback="riden_psu")
    ip_to_identity_cache_timeout_secs = config.getfloat(section="GENERAL", option="ip_to_identity_cache_timeout_secs", fallback=0)
    mqtt_reconnect_delay_secs = config.getfloat(section="GENERAL", option="mqtt_reconnect_delay_secs", fallback=5)
    set_clock_on_connection = config.getboolean(section="GENERAL", option="set_clock_on_connection", fallback=True)

    # Extract config - PSUs
    psu_identity_to_name = {}
    if config.has_section("PSUS"):
        psus_section = config["PSUS"]
        psu_identity_to_name = dict(psus_section.items())

    # Check hostname
    if hostname is None:
        logging.error("Config must contain MQTT hostname at minimum")
        sys.exit(1)

    # Set log level
    logging.getLogger().setLevel(getattr(logging, log_level.upper()))

    # Construct service
    mqtt_bridge = RD60xxToMQTT(hostname, port,
                               client_id=client_id,
                               username=username,
                               password=password,
                               ca_cert=ca_cert,
                               client_cert=client_cert,
                               client_key=client_key,
                               insecure=insecure,
                               mqtt_base_topic=mqtt_base_topic,
                               psu_identity_to_name=psu_identity_to_name,
                               ip_to_identity_cache_timeout_secs=ip_to_identity_cache_timeout_secs,
                               mqtt_reconnect_delay_secs=mqtt_reconnect_delay_secs,
                               set_clock_on_connection=set_clock_on_connection)

    # Run service
    asyncio.run(mqtt_bridge.run())

if __name__ == "__main__":
    main()
