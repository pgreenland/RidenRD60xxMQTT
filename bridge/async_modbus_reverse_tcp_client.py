from collections.abc import Callable
import asyncio
import platform
import socket

from pymodbus.client.base import ModbusBaseClient
from pymodbus.framer.base import FramerType
from pymodbus.pdu import ModbusPDU
from pymodbus.transport import CommParams, CommType

class AsyncModbusReverseTcpClient(ModbusBaseClient, asyncio.Protocol):
    """**AsyncModbusTcpClient**.

    Fixed parameters:

    :param client_connected_cb: Callback on client connection (new client arriving)
    :param client_disconnected_cb: Callback for client disconnection (old client leaving)

    Common optional parameters:

    :param framer: Framer enum name
    :param timeout: Timeout for connecting and receiving data, in seconds (use decimals for milliseconds).
    :param retries: Max number of retries per request.
    :param trace_packet: Called with bytestream received/to be sent
    :param trace_pdu: Called with PDU received/to be sent

    Example::

        from reverse_tcp import AsyncModbusReverseTcpClient

        def modbus_client_connected(client, transport):

            # Handle new client connection
            peername = transport.get_extra_info('peername')
            print('Connection from {}'.format(peername))

        def modbus_client_disconnected(client):

            # Handle client disconnection
            print("Client disconnected")

        async def main():
            # Retrieve IOLoop
            loop = asyncio.get_running_loop()

            # Create TCP server, waiting for clients to connect
            server = await loop.create_server(
                lambda: AsyncModbusReverseTcpClient(modbus_client_connected, modbus_client_disconnected),
                '0.0.0.0', 8080
            )

            async with server:
                await server.serve_forever()

            asyncio.run(main())

    Please refer to :ref:`Pymodbus internals` for advanced usage.
    """

    def __init__(
        self,
        client_connected_cb,
        client_disconnected_cb,
        framer: FramerType = FramerType.SOCKET,
        timeout: float = 1.0,
        retries: int = 3,
        trace_packet: Callable[[bool, bytes], bytes] | None = None,
        trace_pdu: Callable[[bool, ModbusPDU], ModbusPDU] | None = None,
    ) -> None:
        """Initialize Asyncio Modbus Reverse TCP Client."""

        # Store callbacks
        self._client_connected_cb = client_connected_cb
        self._client_disconnected_cb = client_disconnected_cb

        # Force comms type and clear reset delay, preventing "client" from attempting to reconnect on connection loss
        comm_params = CommParams(
            comm_type=CommType.TCP,
            reconnect_delay=0, # Clear reset delay, preventing "client" from attempting to reconnect on connection loss
            timeout_connect=timeout # Connection timeout (used for communication retries in this case)
        )

        # Init parents
        asyncio.Protocol.__init__(self)
        ModbusBaseClient.__init__(
            self,
            framer=framer,
            retries=retries,
            comm_params=comm_params,
            trace_packet=trace_packet,
            trace_pdu=trace_pdu,
            trace_connect=None
        )

    def connection_made(self, transport):
        """Handle new connection"""

        # Update our conn_name and transaction manager with peer info
        host, port = transport.get_extra_info('peername')
        self.comm_params.comm_name = f"{host}:{port}"
        self.ctx.comm_params.comm_name = self.comm_params.comm_name

        # Provide transport to transaction manager
        self.ctx.transport = transport

        # Retrieve socket
        sock = transport.get_extra_info("socket")

        # Enable keepalive, to poke remote device periodically when idle
        if platform.system() == "Linux":
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1) # enable keepalive
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 5) # secs idle time before starting probes
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 2) # secs between probes
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 10) # number of probes

            # Set user timeout to handle device disconnect
            # This option limits how long transmitted data may remain unacknowledged
            # before the connection is closed
            # Set as recommended by cloudflare: https://blog.cloudflare.com/when-tcp-sockets-refuse-to-die
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_USER_TIMEOUT, 15000) # ms

        elif platform.system() == "Darwin":
            TCP_KEEPALIVE = 0x10
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            sock.setsockopt(socket.IPPROTO_TCP, TCP_KEEPALIVE, 5)

        elif platform.system() == "Windows":
            sock.ioctl(socket.SIO_KEEPALIVE_VALS, (1, 5 * 1000, 2 * 1000)) # enable, ms idle time before starting probes, ms between probes

        # Pass to transaction manager
        self.ctx.callback_connected()

        # Notify via callback
        self._client_connected_cb(self, transport)

    def data_received(self, data):
        """Handle received data"""

        # Pass to transaction manager
        self.ctx.callback_data(data=data)

    def connection_lost(self, exc):
        """Handle closed connection"""

        # Pass to transaction manager
        self.ctx.connection_lost(exc)

        # Notify via callback
        self._client_disconnected_cb(self)
