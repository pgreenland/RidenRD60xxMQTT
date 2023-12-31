from typing import Any
import asyncio
import platform
import socket

from pymodbus.client.base import ModbusBaseClient
from pymodbus.framer import Framer
from pymodbus.transport import CommType

class AsyncModbusReverseTcpClient(ModbusBaseClient, asyncio.Protocol):
    """**AsyncModbusTcpClient**.

    Fixed parameters:

    :param client_connected_cb: Callback on client connection (new client arriving)
    :param client_disconnected_cb: Callback for client disconnection (old client leaving)

    Common optional parameters:

    :param framer: Framer enum name
    :param timeout: Timeout for a request, in seconds.
    :param retries: Max number of retries per request.
    :param retry_on_empty: Retry on empty response.
    :param broadcast_enable: True to treat id 0 as broadcast address.
    :param no_resend_on_retry: Do not resend request when retrying due to missing response.
    :param kwargs: Experimental parameters.

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
        framer: Framer = Framer.SOCKET,
        **kwargs: Any,
    ) -> None:
        """Initialize Asyncio Modbus Reverse TCP Client."""

        # Store callbacks
        self._client_connected_cb = client_connected_cb
        self._client_disconnected_cb = client_disconnected_cb

        # Force comms type
        kwargs["CommType"] = CommType.TCP

        # Clear reset delay, preventing "client" from attempting to reconnect on connection loss
        kwargs["reconnect_delay"] = 0

        # Init parents
        asyncio.Protocol.__init__(self)
        ModbusBaseClient.__init__(
            self,
            framer,
            **kwargs,
        )

    async def connect(self):
        """Connect to the modbus remote host, override parent implementation to supress"""

        # Assume we're always connected, until a socket error disconnects us
        return True

    def close(self, reconnect: bool = False) -> None:
        """Close connection, override parent implementation to supress reconnect logic."""

        self.transport_close()

    def connection_made(self, transport):
        """Handle new connection"""

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

        # Pass to parent
        super().connection_made(transport)

        # Notify via callback
        self._client_connected_cb(self, transport)

    def connection_lost(self, exc):
        """Handle closed connection"""

        # Notify via callback
        self._client_disconnected_cb(self)

        # Pass to parent
        super().connection_lost(exc)
