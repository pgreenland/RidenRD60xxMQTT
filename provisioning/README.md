# Provisioning

## Introduction

This directory contains a python script, which implements the provisioning protocol used by the power supply.

## Technical Details

The optional Wi-Fi modules supplied with RuiDeng Riden RD60xx power supply units (at least the few I own) are [Ai Thinker ESP-12Fs](http://www.ai-thinker.com/pro_view-58.html).

The Ai Thinker ESP-12F is based around the Espressif ESP8266 Wi-Fi module, with custom firmware, making it controllable via AT command, as indicated by its general [datasheet](https://docs.ai-thinker.com/_media/esp8266/docs/esp-12f_product_specification_en.pdf).

The provisioning technology used is builtin to the ESP8266, in the form of Espressif's [ESP-Touch](https://www.espressif.com/en/products/software/esp-touch/overview) protocol.

When connecting a power supply to a Wi-Fi network, presumably (I've not snooped on the UART interface) the PSU commands the module to execute the ESP-Touch pairing process. After which it extracts the information needed to connect. Before connecting to the Wi-Fi network and starting communication with the PSU's companion application.

The ESP-Touch process allows for a network SSID, network password, access point BSSID and IP address to be advertised to a supported system without the need for the advertising device to leave its network.

It does this by implementing what could best be described as a side-channel attack. Deliberately leaking information from within an encrypted system, in this case to advertise the credentials of the network.

Before the PSU joins the Wi-Fi network it's able to monitor 802.11 packets being transmitted between hosts and access points, but isn't able to decrypt them. It can however monitor the lengths the encrypted payloads carried by these packets.

The pairing process involves encoding the required information via the transmission of UDP packets of varying lengths within the encrypted network. Something that can easily be achieved from an application within user space. The data content of the packets transmitted is irrelivant (as the PSU can't decrypt them) but a small amount of information can be encoded by modifying the length of each packet transmitted.

The packets seen by the PSU can be through of as being length + overhead bytes long, where overhead is a fixed value added by the encryption method in use.

A training signal is therefore included, with a repeated sequence of lengths being sent. This allows the PSU to identify a candidate network to monitor.

A separate data stream is then sent as a series of broadcast UDP packets, from which the PSU is able to recover the encoded information.

Espressif thankfully provide example iOS and Android applications demonstrating this process. The [Android version](https://github.com/EspressifApp/EsptouchForAndroid/blob/1ed99af52c4c25a85feffeb231c433dde9535142/esptouch/src/main/java/com/espressif/iot/esptouch/EsptouchTask.java) was used as a reference to create the provisioning script here.

The RuiDeng Riden use the ESP-Touch provisioning process in a slightly odd way.

A single execution of the ESP-Touch process allows for an SSID, password, BSSID and IP address (for the device to contact once connected) to be transferred.

The PSU makes use of two iterations. The first iteration it transmits the IP address of the mobile device in place of the network password. The second iteration it transmits the actual network password in the password field. Why they didn't use the IP field, dedicated for this purpose I've no idea.

If using the official app it includes a button/checkbox which the user is asked to select when the PSU displays an IP address. The app switches from the first to second iteration of the algorithm when this input is provided.

However this means that it's easy to advertise the IP address that the PSU should connect to as implemented by this script.

## Launching

The script should be run on a machine with a Wi-Fi card connected to the 2.4Ghz network which the PSU should connect to.

With this in place it can ran as follows. Replacing `<SSID>` with the Wi-Fi network SSID to connect to, replacing `<PASSWORD>` with the network password and `<ENDPOINT IP>` with the IP address of the computer running the bridge application to connect to:

```
python3 provision.py '<SSID>' '<PASSWORD>' '<ENDPOINT IP>'
```

If you're using a machine with multiple network adapters, for example with Wired Ethernet alongside Wi-Fi, you'll need to provide an additional argument `--adapter_ip <IP>` replacing `<IP>` with the IP address assigned to your Wi-Fi adapter. This allows the script to send its UDP packets via the correct interface.

Once running the script should output:

```
Please press enter when power supply displays message 'Connecting wifi'...
```

On the PSU:

* Enter the menu via `Shift + 0`.
* Navigate to `Communication Interface`.
* Ensure `WiFi` is selected.
* Exit the menu.

Power cycle the PSU, via the front panel power button.

Now when booting up you should see a "WiFi Config" dialog.

If the PSU has previously connected to WiFi this dialog may include a reset button, if so, press the left arrow followed by enter to reset the current network configuration.

With the script running wait for the IP provided in `<ENDPOINT IP>` to appear on the screen. When this happens press enter as indicated by the script. This triggers the second part of the paring process.

The script should output the following

```
Please press enter when power supply displays message 'Connecting wifi'...
Please press enter when power supply displays message 'Connecting server'...
```

Once complete the PSU should display "Connecting server", indicating that it's connected to the Wi-Fi and is now attempting to connect to the IP provided. The script prompts for enter to be pressed again when this is displayed, at which point it exits.

Assuming the bridge application is already running on the machine with the provided IP the PSU should connect, appearing in its log.

The PSU should retain this configuration and connect to the network and provided IP on the next power cycle.

I have found however that even with a strong Wi-Fi signal (the access point's in the same room) the PSU occasionally fails to connect at startup and requires power cycling. However once connected it appears to maintain its connection relatively well.
