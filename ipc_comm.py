#!/usr/bin/env python3
"""
Lightweight RFC 6455 WebSocket / Socket IPC Engine
===================================================
100% Python Standard Library (zero external dependencies).
Supports bidirectional JSON messaging between GUI1 and GUI2.
"""

import socket
import threading
import hashlib
import base64
import struct
import json
import time
from typing import Callable, Optional

MAGIC_KEY = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

def encode_ws_frame(payload_str: str, opcode: int = 0x01) -> bytes:
    payload_bytes = payload_str.encode("utf-8")
    length = len(payload_bytes)
    header = bytearray([0x80 | opcode])
    if length <= 125:
        header.append(length)
    elif length <= 65535:
        header.append(126)
        header.extend(struct.pack("!H", length))
    else:
        header.append(127)
        header.extend(struct.pack("!Q", length))
    return bytes(header) + payload_bytes

def decode_ws_frame(stream) -> Optional[str]:
    try:
        b1 = stream.recv(1)
        if not b1:
            return None
        b2 = stream.recv(1)
        if not b2:
            return None
        
        byte1 = b1[0]
        byte2 = b2[0]
        
        opcode = byte1 & 0x0F
        if opcode == 0x08: # close
            return None
        
        masked = (byte2 & 0x80) != 0
        payload_len = byte2 & 0x7F
        
        if payload_len == 126:
            data = stream.recv(2)
            payload_len = struct.unpack("!H", data)[0]
        elif payload_len == 127:
            data = stream.recv(8)
            payload_len = struct.unpack("!Q", data)[0]
            
        mask_key = b""
        if masked:
            mask_key = stream.recv(4)
            
        payload = bytearray()
        remaining = payload_len
        while remaining > 0:
            chunk = stream.recv(min(remaining, 4096))
            if not chunk:
                break
            payload.extend(chunk)
            remaining -= len(chunk)
            
        if masked:
            unmasked = bytearray(len(payload))
            for i in range(len(payload)):
                unmasked[i] = payload[i] ^ mask_key[i % 4]
            return unmasked.decode("utf-8", errors="replace")
        else:
            return payload.decode("utf-8", errors="replace")
    except Exception:
        return None

class WebSocketServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 8765, on_message: Optional[Callable] = None):
        self.host = host
        self.port = port
        self.on_message = on_message
        self._server_sock: Optional[socket.socket] = None
        self._clients: list[socket.socket] = []
        self._running = False
        self._lock = threading.Lock()

    def start(self):
        if self._running:
            return
        self._running = True
        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_sock.bind((self.host, self.port))
        self._server_sock.listen(5)
        
        t = threading.Thread(target=self._listen_loop, daemon=True)
        t.start()

    def _listen_loop(self):
        while self._running:
            try:
                client_sock, addr = self._server_sock.accept()
                t = threading.Thread(target=self._handle_client, args=(client_sock,), daemon=True)
                t.start()
            except Exception:
                break

    def _handle_client(self, client_sock: socket.socket):
        # WebSocket Handshake
        try:
            req = client_sock.recv(4096).decode("utf-8", errors="ignore")
            headers = {}
            for line in req.split("\r\n"):
                if ":" in line:
                    k, v = line.split(":", 1)
                    headers[k.strip().lower()] = v.strip()
                    
            sec_key = headers.get("sec-websocket-key")
            if not sec_key:
                client_sock.close()
                return

            accept_val = base64.b64encode(hashlib.sha1((sec_key + MAGIC_KEY).encode("utf-8")).digest()).decode("utf-8")
            handshake = (
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {accept_val}\r\n\r\n"
            )
            client_sock.sendall(handshake.encode("utf-8"))
            
            with self._lock:
                self._clients.append(client_sock)
                
            # Message receiving loop
            while self._running:
                msg = decode_ws_frame(client_sock)
                if msg is None:
                    break
                if self.on_message:
                    try:
                        data = json.loads(msg)
                        self.on_message(data)
                    except Exception:
                        self.on_message({"raw": msg})
        except Exception:
            pass
        finally:
            with self._lock:
                if client_sock in self._clients:
                    self._clients.remove(client_sock)
            try:
                client_sock.close()
            except Exception:
                pass

    def broadcast(self, message_dict: dict):
        payload_str = json.dumps(message_dict)
        frame = encode_ws_frame(payload_str)
        with self._lock:
            dead_clients = []
            for client in self._clients:
                try:
                    client.sendall(frame)
                except Exception:
                    dead_clients.append(client)
            for d in dead_clients:
                self._clients.remove(d)

    def has_clients(self) -> bool:
        with self._lock:
            return len(self._clients) > 0

    def stop(self):
        self._running = False
        if self._server_sock:
            try:
                self._server_sock.close()
            except Exception:
                pass
        with self._lock:
            for c in self._clients:
                try:
                    c.close()
                except Exception:
                    pass
            self._clients.clear()

class WebSocketClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 8765, on_message: Optional[Callable] = None):
        self.host = host
        self.port = port
        self.on_message = on_message
        self._sock: Optional[socket.socket] = None
        self._running = False

    def connect(self, timeout: float = 3.0) -> bool:
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.settimeout(timeout)
            self._sock.connect((self.host, self.port))
            
            key = base64.b64encode(b"AntigravityWsKey123!").decode("utf-8")
            req = (
                f"GET / HTTP/1.1\r\n"
                f"Host: {self.host}:{self.port}\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key}\r\n"
                "Sec-WebSocket-Version: 13\r\n\r\n"
            )
            self._sock.sendall(req.encode("utf-8"))
            resp = self._sock.recv(4096).decode("utf-8", errors="ignore")
            if "101" not in resp:
                self._sock.close()
                return False
                
            self._sock.settimeout(None)
            self._running = True
            
            t = threading.Thread(target=self._recv_loop, daemon=True)
            t.start()
            return True
        except Exception:
            return False

    def _recv_loop(self):
        while self._running:
            msg = decode_ws_frame(self._sock)
            if msg is None:
                break
            if self.on_message:
                try:
                    data = json.loads(msg)
                    self.on_message(data)
                except Exception:
                    self.on_message({"raw": msg})

    def send(self, message_dict: dict) -> bool:
        if not self._sock or not self._running:
            return False
        try:
            # Client frame must be masked according to RFC 6455
            payload_bytes = json.dumps(message_dict).encode("utf-8")
            mask = b"\x12\x34\x56\x78"
            masked_payload = bytearray(len(payload_bytes))
            for i in range(len(payload_bytes)):
                masked_payload[i] = payload_bytes[i] ^ mask[i % 4]
                
            length = len(payload_bytes)
            header = bytearray([0x81]) # fin + text opcode
            if length <= 125:
                header.append(0x80 | length)
            elif length <= 65535:
                header.append(0x80 | 126)
                header.extend(struct.pack("!H", length))
            else:
                header.append(0x80 | 127)
                header.extend(struct.pack("!Q", length))
                
            frame = bytes(header) + mask + bytes(masked_payload)
            self._sock.sendall(frame)
            return True
        except Exception:
            return False

    def close(self):
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
