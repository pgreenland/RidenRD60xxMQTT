"""Home Assistant MQTT Discovery configuration for Riden PSUs"""

import json
import logging

import aiomqtt

logger = logging.getLogger(__name__)

async def publish_discovery_config(
    mqtt_client: aiomqtt.Client,
    mqtt_base_topic: str,
    mqtt_discovery_prefix: str,
    identity: str,
    model: int,
    name: str,
    firmware_version: str
) -> None:
    """
    Publish Home Assistant MQTT Discovery configuration for a PSU

    Args:
        mqtt_client: MQTT client instance for publishing
        mqtt_base_topic: Base MQTT topic for PSU messages
        mqtt_discovery_prefix: Home Assistant discovery prefix
        identity: PSU identity string (e.g., "60181_2317")
        model: PSU model number (e.g., 60181)
        name: Friendly name for the PSU
        firmware_version: Firmware version string
    """

    if not mqtt_client:
        return

    if logger:
        logger.info("Publishing MQTT Discovery config for %s", identity)

    # Extract current rating from model number
    # Model format: VVCCR where VV=voltage, CC=current, R=revision
    # Example: 60301 = 60V, 30A, revision 1
    model_str = str(model)
    current_rating = int(model_str[2:4])

    # Set limits based on Riden PSU specifications
    # All RD60xx models: 60V max output, 62V max OVP
    # Current/OCP: nominal + 0.2A (e.g., 30A � 30.2A max)
    max_voltage = 60.0
    max_current = current_rating + 0.2
    max_ovp = max_voltage + 2.0

    # Device information shared by all entities
    device = {
        "identifiers": [identity],
        "name": name,
        "model": f"RD{model}",
        "manufacturer": "Riden",
        "sw_version": firmware_version
    }

    # State topic for sensors
    state_topic = f"{mqtt_base_topic}/psu/{identity}/state"
    command_topic = f"{mqtt_base_topic}/psu/{identity}/state/set"

    # Availability topic (bridge online/offline status)
    availability_topic = f"{mqtt_base_topic}/bridge/status"

    # Build availability configurations
    # Most entities need BOTH bridge online AND PSU connected
    dual_availability = [
        {
            "topic": availability_topic,
            "payload_available": "online",
            "payload_not_available": "offline"
        },
        {
            "topic": state_topic,
            "value_template": "{{ value_json.connected }}",
            "payload_available": "True",
            "payload_not_available": "False"
        }
    ]

    # The Connected sensor only needs bridge availability
    # (otherwise it would become unavailable when showing disconnected)
    bridge_only_availability = [
        {
            "topic": availability_topic,
            "payload_available": "online",
            "payload_not_available": "offline"
        }
    ]

    # Define all discovery configurations
    configs = []

    # Sensors (read-only)
    sensors = [
        # Device info
        {"name": "Model", "id": "model", "icon": "mdi:chip", "value_template": "{{ value_json.model }}"},
        {"name": "Serial Number", "id": "serial_no", "icon": "mdi:barcode", "value_template": "{{ value_json.serial_no }}"},
        {"name": "Firmware Version", "id": "firmware_version", "icon": "mdi:update", "value_template": "{{ value_json.firmware_version }}"},

        # Temperature
        {"name": "Temperature", "id": "temp_c", "unit": "°C", "device_class": "temperature", "state_class": "measurement", "value_template": "{{ value_json.temp_c }}"},
        {"name": "External Temperature", "id": "ext_temp_c", "unit": "°C", "device_class": "temperature", "state_class": "measurement", "value_template": "{{ value_json.ext_temp_c }}"},

        # Output measurements
        {"name": "Output Voltage", "id": "output_voltage_disp", "unit": "V", "device_class": "voltage", "state_class": "measurement", "icon": "mdi:lightning-bolt", "value_template": "{{ value_json.output_voltage_disp }}", "precision": 3},
        {"name": "Output Current", "id": "output_current_disp", "unit": "A", "device_class": "current", "state_class": "measurement", "icon": "mdi:current-dc", "value_template": "{{ value_json.output_current_disp }}", "precision": 3},
        {"name": "Output Power", "id": "output_power_disp", "unit": "W", "device_class": "power", "state_class": "measurement", "icon": "mdi:flash", "value_template": "{{ value_json.output_power_disp }}", "precision": 2},
        {"name": "Input Voltage", "id": "input_voltage", "unit": "V", "device_class": "voltage", "state_class": "measurement", "icon": "mdi:power-plug", "value_template": "{{ value_json.input_voltage }}", "precision": 2},

        # Status
        {"name": "Protection Status", "id": "protection_status", "icon": "mdi:shield-check", "value_template": "{{ value_json.protection_status }}"},
        {"name": "Output Mode", "id": "output_mode", "icon": "mdi:sine-wave", "value_template": "{{ value_json.output_mode | upper }}"},
        {"name": "Current Range", "id": "current_range", "unit": "A", "state_class": "measurement", "icon": "mdi:gauge", "value_template": "{% if value_json.current_range is defined %}{{ 6 if value_json.current_range == 0 else 12 }}{% else %}0{% endif %}"},

        # Battery
        {"name": "Battery Mode", "id": "battery_mode", "icon": "mdi:battery-charging", "value_template": "{{ value_json.battery_mode }}"},
        {"name": "Battery Voltage", "id": "battery_voltage", "unit": "V", "device_class": "voltage", "state_class": "measurement", "icon": "mdi:battery", "value_template": "{{ value_json.battery_voltage }}", "precision": 2},
        {"name": "Battery Amp Hours", "id": "battery_ah", "unit": "Ah", "state_class": "measurement", "icon": "mdi:battery-charging-100", "value_template": "{{ value_json.batt_ah }}", "precision": 3},
        {"name": "Battery Watt Hours", "id": "battery_wh", "unit": "Wh", "device_class": "energy", "state_class": "measurement", "icon": "mdi:lightning-bolt-circle", "value_template": "{{ value_json.batt_wh }}", "precision": 3},
    ]

    for sensor in sensors:
        config = {
            "name": sensor['name'],
            "unique_id": f"riden_{identity}_{sensor['id']}",
            "object_id": f"riden_{identity}_{sensor['id']}",
            "state_topic": state_topic,
            "value_template": sensor["value_template"],
            "availability": dual_availability,
            "device": device
        }
        if "unit" in sensor:
            config["unit_of_measurement"] = sensor["unit"]
        if "device_class" in sensor:
            config["device_class"] = sensor["device_class"]
        if "state_class" in sensor:
            config["state_class"] = sensor["state_class"]
        if "icon" in sensor:
            config["icon"] = sensor["icon"]
        if "precision" in sensor:
            config["suggested_display_precision"] = sensor["precision"]

        topic = f"{mqtt_discovery_prefix}/sensor/riden_{identity}/{sensor['id']}/config"
        configs.append((topic, config))

    # Binary sensor for connection status
    # Uses bridge-only availability so it can show disconnected state
    connected_sensor = {
        "name": "Connected",
        "unique_id": f"riden_{identity}_connected",
        "object_id": f"riden_{identity}_connected",
        "state_topic": state_topic,
        "value_template": "{{ value_json.connected }}",
        "payload_on": True,
        "payload_off": False,
        "device_class": "connectivity",
        "icon": "mdi:connection",
        "availability": bridge_only_availability,
        "device": device
    }
    topic = f"{mqtt_discovery_prefix}/binary_sensor/riden_{identity}/connected/config"
    configs.append((topic, connected_sensor))

    # Switch for output enable control
    output_switch = {
        "name": "Output",
        "unique_id": f"riden_{identity}_output",
        "object_id": f"riden_{identity}_output",
        "state_topic": state_topic,
        "command_topic": command_topic,
        "value_template": "{{ value_json.output_enable }}",
        "payload_on": '{"output_enable": true}',
        "payload_off": '{"output_enable": false}',
        "state_on": True,
        "state_off": False,
        "icon": "mdi:power",
        "availability": dual_availability,
        "device": device
    }
    topic = f"{mqtt_discovery_prefix}/switch/riden_{identity}/output/config"
    configs.append((topic, output_switch))

    # Number controls (using dynamic limits based on PSU model)
    numbers = [
        {"name": "Set Voltage", "id": "set_voltage", "min": 0, "max": max_voltage, "step": 0.01, "unit": "V", "device_class": "voltage", "icon": "mdi:lightning-bolt", "value_template": "{{ value_json.output_voltage_set }}", "command_template": '{"output_voltage_set": {{ value }} }'},
        {"name": "Set Current", "id": "set_current", "min": 0, "max": max_current, "step": 0.01, "unit": "A", "device_class": "current", "icon": "mdi:current-dc", "value_template": "{{ value_json.output_current_set }}", "command_template": '{"output_current_set": {{ value }} }'},
        {"name": "OVP", "id": "set_ovp", "min": 0, "max": max_ovp, "step": 0.01, "unit": "V", "device_class": "voltage", "icon": "mdi:shield-alert", "value_template": "{{ value_json.ovp }}", "command_template": '{"ovp": {{ value }} }'},
        {"name": "OCP", "id": "set_ocp", "min": 0, "max": max_current, "step": 0.01, "unit": "A", "device_class": "current", "icon": "mdi:shield-alert", "value_template": "{{ value_json.ocp }}", "command_template": '{"ocp": {{ value }} }'},
        {"name": "Update Period", "id": "set_period", "min": 0, "max": 60, "step": 0.1, "unit": "s", "icon": "mdi:timer", "value_template": "{{ value_json.period }}", "command_template": '{"period": {{ value }} }'},
    ]

    for number in numbers:
        config = {
            "name": number['name'],
            "unique_id": f"riden_{identity}_{number['id']}",
            "object_id": f"riden_{identity}_{number['id']}",
            "state_topic": state_topic,
            "command_topic": command_topic,
            "value_template": number["value_template"],
            "command_template": number["command_template"],
            "min": number["min"],
            "max": number["max"],
            "step": number["step"],
            "mode": "box",
            "availability": dual_availability,
            "device": device
        }
        if "unit" in number:
            config["unit_of_measurement"] = number["unit"]
        if "device_class" in number:
            config["device_class"] = number["device_class"]
        if "icon" in number:
            config["icon"] = number["icon"]

        topic = f"{mqtt_discovery_prefix}/number/riden_{identity}/{number['id']}/config"
        configs.append((topic, config))

    # Buttons
    buttons = [
        {"name": "Request State", "id": "request_state", "icon": "mdi:refresh", "payload": '{"query": true}', "command_topic": f"{mqtt_base_topic}/psu/{identity}/state/get"},
    ]

    for button in buttons:
        config = {
            "name": button['name'],
            "unique_id": f"riden_{identity}_{button['id']}",
            "object_id": f"riden_{identity}_{button['id']}",
            "command_topic": button.get("command_topic", command_topic),
            "payload_press": button["payload"],
            "icon": button["icon"],
            "availability": dual_availability,
            "device": device
        }

        topic = f"{mqtt_discovery_prefix}/button/riden_{identity}/{button['id']}/config"
        configs.append((topic, config))

    # Publish all configurations
    try:
        for topic, config in configs:
            await mqtt_client.publish(topic, payload=json.dumps(config), retain=True)
        if logger:
            logger.info("Published %d MQTT Discovery configs for %s", len(configs), identity)
    except aiomqtt.MqttError as e:
        if logger:
            logger.error("Failed to publish MQTT Discovery configs: %s", e)
