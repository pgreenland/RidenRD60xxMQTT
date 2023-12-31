import json

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

class ESPTouchDecode:
    """
    Attempt to decode ESPTouch UDP packets, exported from Wireshark capture as JSON
    For example, capture packets from wifi interface, filter by IP 255.255.255.255 and port 7001, export as JSON.
    """

    @staticmethod
    def decode(filename:str):
        """Decode file and dump and credentials found"""

        with open(filename, "r") as f:
            json_data = json.load(f)

        # Extract packet lengths from capture
        lens = []
        for pkt in json_data:
            udp_len = int(pkt["_source"]["layers"].get("data", {}).get("data.len", "0"))
            lens.append(udp_len)

        # Split lengths into msb and lsb bytes
        tuples = []
        for l in lens:
            # Subtract magic +40 added to packet lengths
            l -= 40

            # Split length into bytes
            upper = (l >> 8) & 0xff
            lower = (l >> 0) & 0xff

            tuples.append((upper, lower))

        # Extract data from tuples
        extracted_data = {}
        for i in range(1, len(tuples) - 1):
            # Place a sliding window over the packet lengths
            a_index, a_data = tuples[i - 1]
            b_index, b_data = tuples[i]
            c_index, c_data = tuples[i + 1]

            # Check for expected sequence
            if a_index == 0 and b_index == 1 and c_index == 0:
                # Found a sequence, attempt to extract data
                high_crc = (a_data >> 4) & 0x0f
                high_data = (a_data >> 0) & 0x0f

                low_crc = (c_data >> 4) & 0x0f
                low_data = (c_data >> 0) & 0x0f

                crc = (high_crc << 4) | low_crc
                data = (high_data << 4) | low_data

                seqno = b_data

                # Verify CRC
                calc = EspTouchCRC()
                calc.update(data.to_bytes())
                calc_crc = calc.update(seqno.to_bytes())
                crc_good = (calc_crc == crc)

                if crc_good:
                    # So far so good
                    #print(f"SEQ: {seqno}, DATA: {data:02X}, CRC: {crc:02X}, CRCOK: {crc_good}")

                    # Add sequence number and byte to extracted data buffer, incrementing count if already seen
                    index_data = (seqno, data)

                    # Ensure data stored
                    if not index_data in extracted_data:
                        extracted_data[index_data] = 0

                    # Increment number of times seen
                    extracted_data[index_data] += 1

        # Filter data by number of times each entry is seen
        filtered_data = {}
        for index_data, count in extracted_data.items():
            index, data = index_data

            if not index in filtered_data:
                # First time data seen, add it
                filtered_data[index] = (data, count)

            if count > filtered_data[index][1]:
                # This version of the same index occurred more times, prefer it
                filtered_data[index] = (data, count)

        # Extract raw data from filtered
        raw_data = []
        last_index = -1
        for index in sorted(filtered_data.keys()):
            # Process next data byte, having sorted the keys array (data byte index)
            data = filtered_data[index][0]
            count = filtered_data[index][1]

            #print(f"{key} = {data:02X} ({count})")
            #print(f"{data:02X}", end='')

            if index != (last_index + 1):
                # Current index doesn't match the next expected one
                raise Exception("Missing data!!")

            # Add byte to buffer
            raw_data.append(data)

            # Update last index
            last_index = index
        #print("")

        # Dump buffer
        print(bytes(raw_data), end='')
        # print(bytes(raw_data).hex())
        #print(bytes(raw_data).decode(errors="ignore"))

        # Extract fields
        # Note: Could validate xor checksum too
        total_len = raw_data[0]
        password_len = raw_data[1]
        ssid_crc = raw_data[2]
        bssid_crc = raw_data[3]
        total_xor = raw_data[4]
        next = 5
        ip_addr = raw_data[next:next+4]
        next += 4
        password = raw_data[next:next+password_len]
        next += password_len
        ssid_len = total_len - password_len - 4 - 5
        ssid = raw_data[next:next+ssid_len]
        next += ssid_len
        bssid = raw_data[next:next+6]

        # Print extracted fields
        print(f"Total Len: {total_len}")
        print(f"Pass Len: {password_len}")
        print(f"SSID Len: {ssid_len}")
        print(f"IP: {ip_addr}")
        print(f"Password: {bytes(password).decode()}")
        print(f"SSID: {bytes(ssid).decode()}")
        print(f"BSSID: {bytes(bssid).hex()}")

if __name__ == "__main__":
    # Decode test file
    ESPTouchDecode.decode("packets.json")
