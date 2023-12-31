from typing import List
import argparse
import ipaddress
import socket
import struct
import threading
import time

# Based on espressif example app (Android version)
# https://github.com/EspressifApp/EsptouchForAndroid/blob/master/esptouch/src/main/java/com/espressif/iot/esptouch/protocol/EsptouchGenerator.java

class EspTouchCRC:
    """
    Implements CRC algorithm used by ESPTouch
    This is CRC-8/MAXIM / Dallas One Wire CRC.
    Polynomial = 0x31, input reflected, output reflected, no output xor
    """
    CRC_POLYNOM = 0x8c # 0x31 reflected

    # Static table
    crcTable = None

    def __init__(self, init=0):
        """Construct CRC instance"""

        # Prepare table on first call
        if EspTouchCRC.crcTable is None:
            EspTouchCRC.crcTable = [0] * 256
            for i in range(256):
                crc = i
                for _ in range(8):
                    if ((crc & 0x01) != 0):
                        crc = (crc >> 1) ^ EspTouchCRC.CRC_POLYNOM
                    else:
                        crc >>= 1
                EspTouchCRC.crcTable[i] = crc

        # Set current value from initial
        self.value = init

    def update(self, data:bytes):
        """Update CRC with provided data"""

        for d in data:
            # xor in new data and update value using lookup table
            d ^= self.value
            self.value = (EspTouchCRC.crcTable[d & 0xff] ^ (self.value << 8)) & 0xFFFF

        # Return new CRC value
        return self.value & 0xFF

class ESPTouchDataCode:
    """Represents a data byte to be encoded and transmitted"""

    # Max byte index
    MAX_INDEX = 127

    def __init__(self, data:int, index:int):
        """Constructor"""

        if (index > self.MAX_INDEX):
            raise Exception(f"index must be <= {self.MAX_INDEX}")

        # Split byte into two nibbles
        self.data_high, self.data_low = self._split_byte(data)

        # CRC byte and index
        crc = EspTouchCRC().update(data.to_bytes() + index.to_bytes())

        # Split crc into two nibbles
        self.crc_high, self.crc_low = self._split_byte(crc)

        # Store index as sequence number
        self.seq_no = index

    def to_bytes(self) -> bytes:
        """Retreive bytes representing data code"""

        buffer = bytearray()
        buffer.append(0x00)
        buffer.append(self._combine_byte(self.crc_high, self.data_high))
        buffer.append(0x01)
        buffer.append(self.seq_no)
        buffer.append(0x00)
        buffer.append(self._combine_byte(self.crc_low, self.data_low))
        return bytes(buffer)

    def _split_byte(self, data:bytes):
        """Split byte into its upper and lower nibble"""

        high = (data & 0xF0) >> 4
        low = (data & 0x0F) >> 0

        high = struct.pack("B", high)[0]
        low = struct.pack("B", low)[0]

        return (high, low)

    def _combine_byte(self, high, low) -> int:
        """Combine upper and lower nibble into byte"""

        return ((high & 0x0f) << 4) | (low & 0x0f)

class ESPTouch:
    """Implementation of ESPTouch device provisioning algorithm"""

    def __init__(self, ssid, password, ip=None, bssid="00:00:00:00:00:00") -> None:
        """Construct instance"""

        # Store arguments
        self._ssid = ssid
        self._password = password
        self._ip = ip
        self._bssid = bssid

        # Open, bind and "connect" UDP socket
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        if self._ip is not None:
            # Bind to specified IP
            self._sock.bind((self._ip, 0))
        self._sock.connect(("255.255.255.255", 7001))
        if self._ip is None:
            # Retrieve IP that the OS has bound the socket to
            self._ip = self._sock.getsockname()[0]

        # Convert arguments to binary
        ssid_enc = self._ssid.encode()
        password_enc = self._password.encode()
        ip_enc = ipaddress.ip_address(self._ip).packed
        bssid_enc = bytes.fromhex(self._bssid.replace(":", ""))

        # Generate guide code
        guide_code_packet_lengths = [515, 514, 513, 512]
        self._guide_code_packets = [b"\x01" * i for i in guide_code_packet_lengths]

        # Generate data code
        # Data = total len(1 byte) + apPwd len(1 byte) + SSID CRC(1 byte) + BSSID CRC(1 byte) + TOTAL XOR(1 byte) + ipAddress(4 byte) + apPwd + apSsid apPwdLen <= 105 at the moment

        # Reset xor
        total_xor = 0

        # Retrieve password length
        password_len = len(password_enc)

        # CRC SSID
        ssid_crc = EspTouchCRC().update(ssid_enc)

        # CRC BSSID
        bssid_crc = EspTouchCRC().update(bssid_enc)

        # Retrive ssid length
        ssid_len = len(ssid_enc)

        # Retrieve IP address length
        ip_len = len(ip_enc)

        # Calculate total length
        extra_head_len = 5
        total_len = extra_head_len + ip_len + password_len + ssid_len

        # Prepare list of data codex
        codes:List[ESPTouchDataCode] = []

        codes.append(ESPTouchDataCode(total_len.to_bytes()[0], 0))
        total_xor ^= total_len

        codes.append(ESPTouchDataCode(password_len.to_bytes()[0], 1))
        total_xor ^= password_len

        codes.append(ESPTouchDataCode(ssid_crc.to_bytes()[0], 2))
        total_xor ^= ssid_crc

        codes.append(ESPTouchDataCode(bssid_crc.to_bytes()[0], 3))
        total_xor ^= bssid_crc

        # Data index 4 null

        # Add IP
        for i in range(ip_len):
            b = ip_enc[i]
            codes.append(ESPTouchDataCode(b, extra_head_len + i))
            total_xor ^= b

        # Add password
        for i in range(password_len):
            b = password_enc[i]
            codes.append(ESPTouchDataCode(b, extra_head_len + ip_len + i))
            total_xor ^= b

        # Add SSID
        for i in range(ssid_len):
            b = ssid_enc[i]
            codes.append(ESPTouchDataCode(b, extra_head_len + ip_len + password_len + i))
            total_xor ^= b

        # Add total xor
        codes.append(ESPTouchDataCode(total_xor, 4))

        # Add BSSID
        bssid_insert_index = extra_head_len
        for i in range(len(bssid_enc)):
            b = bssid_enc[i]
            code = ESPTouchDataCode(b, total_len + i)
            if (bssid_insert_index >= len(codes)):
                code.append(code)
            else:
                codes.insert(bssid_insert_index, code)
            bssid_insert_index += 4

        # Retrieve complete datum code as bytes
        datum_code_bytes = bytearray()
        for code in codes:
            datum_code_bytes.extend(code.to_bytes())

        # Convert bytes to packet lengths
        extra_length = 40
        datum_code_packet_lengths = []
        for i in range(len(datum_code_bytes) // 2):
            high = datum_code_bytes[i * 2 + 0]
            low = datum_code_bytes[i * 2 + 1]
            high_low = ((high & 0xFF) << 8) | ((low & 0xFF) << 0)
            datum_code_packet_lengths.append(high_low + extra_length)

        # Generate packets based on lengths
        self._datum_code_packets = [b"\x01" * i for i in datum_code_packet_lengths]

        # Construct thread to run
        self._thread = threading.Thread(target=self._thread_target, daemon=True)
        self._should_be_running = True

    def start(self):
        """Transmit ESP touch messages in background thread until stopped"""

        # Start provisioning thread
        self._thread.start()

    def stop(self):
        """Stop transmitting"""

        # Request provisioning thread stop, waiting for it to do so by joining with it
        self._should_be_running = False
        self._thread.join()

    def _thread_target(self):
        """Entrypoint for thread"""

        # Define timeouts and intervals, lifting from demo app
        interval_guide_code = 8
        interval_data_code = 8
        timeout_guide_code = 2000
        timeout_data_code = 4000

        # Send packets until stopped
        index = 0
        increment = 3
        #print(f"Sending - SSID: {self._ssid}, Password: {self._password[0]}xxx{self._password[-1]} IP: {self._ip} BSSID: {self._bssid}")
        while self._should_be_running:
            # Send guide code
            start = time.time()
            while self._should_be_running and (time.time() - start) < (timeout_guide_code / 1000.0):
                for datagram in self._guide_code_packets:
                    self._sock.send(datagram)
                    time.sleep(interval_guide_code / 1000.0)

            # Send data
            start = time.time()
            while self._should_be_running and (time.time() - start) < (timeout_data_code / 1000.0):
                for datagram in self._datum_code_packets[index:index+increment]:
                    self._sock.send(datagram)
                    time.sleep(interval_data_code / 1000.0)
                index = (index + increment) % len(self._datum_code_packets)

def main():
    """Entrypoint"""

    try:
        # Parse arguments
        parser = argparse.ArgumentParser(description="Provision Riden RD60xx power supply with Wi-Fi network details and data endpoint address.")
        parser.add_argument("ssid", type=str, help="SSID of the Wi-Fi network")
        parser.add_argument("password", type=str, help="Password of the Wi-Fi network")
        parser.add_argument("endpoint_ip", type=str, help="IP address of the server to connect to on the Wi-Fi network")
        parser.add_argument("--adapter_ip", type=str, help="IP address of the local Wi-Fi adapter to transmit provisioning data on")
        args = parser.parse_args()

        # Generate one data stream for IP and another for password
        instance_ip = ESPTouch(args.ssid, args.endpoint_ip, args.adapter_ip)
        instance_pass = ESPTouch(args.ssid, args.password, args.adapter_ip)

        # Send IP stream first
        instance_ip.start()

        # Pause while IP transmitted
        print("Please press enter when power supply displays message 'Connecting wifi'...", end='', flush=True)
        input()

        # Stop IP stream and start password stream
        instance_ip.stop()
        instance_pass.start()

        # Pause while password
        print("Please press enter when power supply displays message 'Connecting server'...", end='', flush=True)
        input()

        # Stop IP stream (note we don't bother listening for the confirmations transmitted by the power supply)
        instance_pass.stop()

    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
