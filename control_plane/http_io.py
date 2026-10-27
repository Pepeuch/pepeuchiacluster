"""Deadline-bound socket reader, shared by the local HTTP server and worker.

No retries, no real wait in tests: monotonic clock/socket are injectable.
"""

import time


class DeadlineInput:
    def __init__(self, connection, *, seconds=5, clock=time.monotonic, own_socket=False):
        self.connection = connection
        self.clock = clock
        self.deadline = clock() + seconds
        self.buffer = bytearray()
        self.closed = False
        self.own_socket = own_socket

    def remaining(self):
        remaining = self.deadline - self.clock()
        if remaining <= 0:
            raise TimeoutError("http_deadline")
        return remaining

    def _receive(self, limit):
        self.connection.settimeout(self.remaining())
        data = self.connection.recv(min(limit, 8192))
        self.remaining()
        return data

    def readline(self, limit=4097):
        if limit < 0:
            limit = 4097
        while True:
            self.remaining()
            position = self.buffer.find(b"\n", 0, limit)
            if position >= 0 or len(self.buffer) >= limit:
                count = position + 1 if position >= 0 else limit
                result = bytes(self.buffer[:count])
                del self.buffer[:count]
                return result
            data = self._receive(limit - len(self.buffer))
            if not data:
                result = bytes(self.buffer)
                self.buffer.clear()
                return result
            self.buffer.extend(data)

    def read(self, size):
        if size < 0:
            raise ValueError("Explicit bounded read required")
        result = bytearray(self.buffer[:size])
        del self.buffer[:size]
        while len(result) < size:
            data = self._receive(size - len(result))
            if not data:
                break
            result.extend(data)
        self.remaining()
        return bytes(result)

    def close(self):
        self.closed = True
        if self.own_socket:
            self.connection.close()

    def flush(self):
        # HTTPResponse flushes its read-only file during early/error close.
        pass


class ResponseInput(DeadlineInput):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.header_bytes = 0

    def readline(self, limit=4097):
        line = super().readline(min(limit, 4097))
        self.header_bytes += len(line)
        if len(line) > 4096 or self.header_bytes > 16384 or not line.endswith(b"\r\n"):
            raise OSError("invalid_response_headers")
        return line


class DeadlineSocket:
    """HTTPConnection socket adapter; the response owns its socket reader."""
    def __init__(self, connection, seconds=5):
        self.connection = connection
        self.reader = ResponseInput(connection, seconds=seconds, own_socket=True)
        self.reader_open = False

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def sendall(self, raw):
        self.connection.settimeout(self.reader.remaining())
        self.connection.sendall(raw)
        self.reader.remaining()

    def makefile(self, mode):
        if mode != "rb":
            raise ValueError("Read-only HTTP stream required")
        self.reader_open = True
        return self.reader

    def close(self):
        # HTTPConnection closes on Connection:close BEFORE body consumption.
        if not self.reader_open:
            self.connection.close()
