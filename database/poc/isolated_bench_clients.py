"""Small stdlib clients for an explicitly selected isolated synthetic bench.

No discovery, credentials lookup, shell, retries, provider or GPU access.
PostgreSQL supports only trust authentication; SQL COPY stays in existing psql.
"""

import base64
import http.client
import json
import socket
import struct
import time


MAX_RESPONSE = 32 * 1024 * 1024


class EngineError(RuntimeError):
    def __init__(self, code, detail=""):
        self.code = str(code)[:64]
        # Bench data is synthetic; never attach headers or authentication.
        self.detail = str(detail).replace("\n", " ")[:240]
        super().__init__(self.code + ": " + self.detail)


class Postgres:
    def __init__(self, host, database="bench", *, port=5432, timeout=30):
        self.socket = socket.create_connection((host, port), timeout=timeout)
        body = struct.pack("!I", 196608) + b"user\0bench\0database\0" + database.encode() + b"\0client_encoding\0UTF8\0\0"
        self.socket.sendall(struct.pack("!I", len(body)+4)+body)
        self.parameters = {}
        try:
            self._receive()
        except BaseException:
            self.close()
            raise

    def _read(self, count):
        parts = []
        while count:
            chunk = self.socket.recv(count)
            if not chunk:
                raise EngineError("pg_connection_closed")
            parts.append(chunk)
            count -= len(chunk)
        return b"".join(parts)

    def _receive(self):
        rows, error, received = [], None, 0
        while True:
            kind = self._read(1)
            size = struct.unpack("!I", self._read(4))[0] - 4
            if size < 0 or size > MAX_RESPONSE or received + size > MAX_RESPONSE:
                raise EngineError("pg_response_limit")
            payload = self._read(size)
            received += size
            if kind == b"R" and payload != b"\0\0\0\0":
                raise EngineError("pg_unexpected_authentication", "Only isolated trust authentication supported")
            if kind == b"S":
                key, val, _ = payload.split(b"\0", 2)
                self.parameters[key.decode()] = val.decode()
            if kind == b"E":
                fields = {field[:1]: field[1:].decode(errors="replace") for field in payload.split(b"\0") if field}
                error = EngineError(fields.get(b"C", "pg_error"), fields.get(b"M", ""))
            if kind == b"D":
                count = struct.unpack("!H", payload[:2])[0]
                pos, row = 2, []
                for _ in range(count):
                    length = struct.unpack("!i", payload[pos:pos+4])[0]
                    pos += 4
                    if length < -1 or pos + max(length, 0) > len(payload):
                        raise EngineError("pg_invalid_row")
                    row.append(None if length == -1 else payload[pos:pos+length].decode())
                    pos += max(0, length)
                rows.append(row)
            if kind in (b"G", b"H", b"W"):
                raise EngineError("pg_copy_not_supported", "Use the bounded psql import seam")
            if kind == b"Z":
                if error:
                    raise error
                return rows

    def sql(self, statement):
        raw = statement.encode("utf-8") + b"\0"
        if len(raw) > MAX_RESPONSE:
            raise EngineError("pg_request_limit")
        self.socket.sendall(b"Q"+struct.pack("!I", len(raw)+4)+raw)
        return self._receive()

    def query(self, statement):
        # One JSON column avoids lossy numeric/null decoding from text rows.
        sql = "SELECT COALESCE(json_agg(q),'[]'::json) FROM ("+statement.rstrip(";\n ")+") q;"
        start = time.perf_counter()
        rows = self.sql(sql)
        elapsed = (time.perf_counter()-start)*1000
        if len(rows) != 1 or len(rows[0]) != 1:
            raise EngineError("pg_query_shape")
        return json.loads(rows[0][0]), elapsed

    def close(self):
        sock = getattr(self, "socket", None)
        if sock is not None:
            sock.close()  # Deliberate TCP closure also tests transaction rollback.
            self.socket = None


class Surreal:
    def __init__(self, host, *, namespace, database, password, port=8000, timeout=30, session=False):
        self.connection = http.client.HTTPConnection(host, port=port, timeout=timeout)
        self.headers = {"Authorization": "Basic " + base64.b64encode(("benchadmin:"+password).encode()).decode(),
                        "Surreal-NS": namespace, "Surreal-DB": database, "Accept": "application/json",
                        "Content-Type": "text/plain"}
        self.auth_mode = "basic_per_request"
        if session:
            try:
                self.authenticate(password)
            except BaseException:
                self.close()
                raise

    def authenticate(self, password):
        # Sign in BEFORE query measurements. Neither body nor token is retained
        # in a report, exception, query parameter, command line or log.
        body = json.dumps({"user":"benchadmin","pass":password}).encode()
        self.connection.request("POST","/signin",body=body,headers={"Accept":"application/json","Content-Type":"application/json"})
        response = self.connection.getresponse()
        raw = response.read(16385)
        if response.status!=200 or len(raw)>16384:
            raise EngineError("surreal_signin_failed")
        try:
            value = json.loads(raw)
            token = value.get("token")
            if value.get("code")!=200 or not isinstance(token,str) or not 20<len(token)<12000 or any(c.isspace() for c in token):
                raise ValueError()
        except (ValueError,AttributeError,TypeError):
            raise EngineError("surreal_invalid_signin_response") from None
        self.headers["Authorization"] = "Bearer "+token
        self.auth_mode = "bearer_session"

    def request(self, method, path, body=None, *, allow_http_error=False):
        start = time.perf_counter()
        self.connection.request(method, path, body=body, headers=self.headers)
        response = self.connection.getresponse()
        raw = response.read(MAX_RESPONSE+1)
        elapsed = (time.perf_counter()-start)*1000
        if len(raw) > MAX_RESPONSE:
            raise EngineError("surreal_response_limit")
        if response.status >= 300 and not allow_http_error:
            raise EngineError("surreal_http_"+str(response.status))
        return response.status, raw, elapsed

    def sql(self, statement):
        body = statement.encode()
        if len(body) > 1024*1024:
            raise EngineError("surreal_request_limit", "SQL HTTP payload exceeds one MiB")
        _, raw, elapsed = self.request("POST", "/sql", body)
        data = json.loads(raw)
        if not isinstance(data, list) or any(not isinstance(r, dict) for r in data):
            raise EngineError("surreal_query_shape")
        for item in data:
            if item.get("status") != "OK":
                raise EngineError("surreal_sql_error", item.get("result", ""))
        self.last_server_times = [str(item.get("time", ""))[:64] for item in data]
        return data, elapsed

    def query(self, statement):
        data, elapsed = self.sql(statement.rstrip(";\n ")+";")
        if len(data) != 1 or not isinstance(data[0].get("result"), list):
            raise EngineError("surreal_query_shape")
        return data[0]["result"], elapsed

    def close(self):
        self.connection.close()
