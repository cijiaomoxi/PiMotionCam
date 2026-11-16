"""Opt-in signed TCP/multicast control with bounded commands and replay checks.

This is a modern PiMotionCam protocol, not an unauthenticated shell interface.
"""

from __future__ import annotations
import hashlib
import hmac
import json
import math
import shlex
import socket
import struct
import threading
import time
import uuid


def sign_message(message, secret):
    body = {k: v for k, v in message.items() if k != "signature"}
    encoded = json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    return hmac.new(secret.encode(), encoded, hashlib.sha256).hexdigest()


def packet(secret, command="", kind="command", **extra):
    body = {
        "id": uuid.uuid4().hex,
        "time": time.time(),
        "type": kind,
        "command": command,
        **extra,
    }
    body["signature"] = sign_message(body, secret)
    return body


def allowed_command(command):
    try:
        words = shlex.split(command)
    except ValueError:
        return False
    if not words or len(words) > 8 or len(command) > 512:
        return False
    verb = words[0]
    if verb == "still":
        return len(words) == 1
    if verb in ("record", "loop", "motion_enable"):
        return len(words) in (2, 3) and words[1] in (
            "on",
            "off",
            "pause",
            "resume",
            "start",
            "stop",
            "manual",
            "toggle",
        )
    if verb == "motion":
        return len(words) in (2, 3) and words[1] == "trigger"
    if verb == "preset":
        return len(words) == 3 and words[1] == "activate"
    if verb in ("tl_start", "tl_hold", "tl_end"):
        return len(words) <= 2
    return False


class ControlServer:
    def __init__(self, config, handler, on_message=None, log=None):
        self.config, self.handler = config, handler
        self.on_message, self.log = on_message, log or (lambda *a: None)
        self._stop = threading.Event()
        self._seen = {}
        self._lock = threading.Lock()
        self._sockets, self._threads = [], []
        self._clients = threading.BoundedSemaphore(4)
        self.error = ""
        self.tcp_address = None

    def dispatch(self, data, peer):
        options = self.config.get("network", default={}) or {}
        secret = str(options.get("secret") or "")
        allowed = options.get("allow_hosts") or ["127.0.0.1"]
        if not secret or peer not in allowed:
            raise PermissionError("Peer is not allowed")
        if len(data) > 8192:
            raise ValueError("Control packet is too large")
        msg = json.loads(data)
        if not isinstance(msg, dict):
            raise ValueError("Invalid control packet")
        signature = str(msg.get("signature", ""))
        if not hmac.compare_digest(signature, sign_message(msg, secret)):
            raise PermissionError("Invalid signature")
        stamp = float(msg.get("time", 0))
        if not math.isfinite(stamp) or abs(time.time() - stamp) > 30:
            raise PermissionError("Expired control packet")
        identity = str(msg.get("id", ""))
        if not identity or len(identity) > 64:
            raise ValueError("Invalid packet ID")
        with self._lock:
            now = time.monotonic()
            self._seen = {
                key: expiry for key, expiry in self._seen.items() if expiry > now
            }
            if identity in self._seen:
                raise PermissionError("Duplicate control packet")
            if len(self._seen) >= 2048:
                raise RuntimeError("Control rate limit reached")
            self._seen[identity] = now + 35
        kind = msg.get("type")
        if kind == "command":
            command = str(msg.get("command", ""))
            if not allowed_command(command):
                raise PermissionError("Command is not permitted over the network")
            result = self.handler(command)
        elif kind == "pkc-message":
            result = str(msg.get("message", ""))[:1024]
            if self.on_message:
                self.on_message(result, peer)
        elif kind == "ack":
            return None
        else:
            raise ValueError("Unknown control packet type")
        return packet(secret, kind="ack", reply_to=identity, result=str(result)[:1024])

    def start(self):
        self.stop()
        self.error = ""
        options = self.config.get("network", default={}) or {}
        if not options.get("tcp_enabled") and not options.get("multicast_enabled"):
            return
        if len(str(options.get("secret") or "")) < 16:
            self.error = "Configure a shared secret of at least 16 characters"
            return
        self._stop.clear()
        try:
            if options.get("tcp_enabled"):
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._sockets.append(sock)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(
                    (
                        str(options.get("tcp_host") or "127.0.0.1"),
                        int(options.get("tcp_port", 3000)),
                    )
                )
                self.tcp_address = sock.getsockname()
                sock.listen(4)
                sock.settimeout(0.3)
                self._launch(self._tcp, sock)
            if options.get("multicast_enabled"):
                sock = socket.socket(
                    socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP
                )
                self._sockets.append(sock)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(("", int(options.get("multicast_port", 22555))))
                member = socket.inet_aton(
                    options.get("multicast_group", "225.0.0.55")
                ) + socket.inet_aton(options.get("interface", "0.0.0.0"))
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, member)
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
                sock.settimeout(0.3)
                self._launch(self._udp, sock)
        except (OSError, ValueError, TypeError) as exc:
            self.error = str(exc)
            self.log("network control: %s" % exc)
            self.stop()

    def _launch(self, fn, *args):
        thread = threading.Thread(
            target=fn, args=args, daemon=True, name="network-control"
        )
        self._threads.append(thread)
        thread.start()

    def _tcp(self, sock):
        while not self._stop.is_set():
            try:
                connection, peer = sock.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            if not self._clients.acquire(blocking=False):
                connection.close()
                continue
            threading.Thread(
                target=self._client, args=(connection, peer[0]), daemon=True
            ).start()

    def _client(self, connection, peer):
        try:
            with connection:
                connection.settimeout(3)
                data = b""
                while (
                    b"\n" not in data and len(data) <= 8192 and not self._stop.is_set()
                ):
                    chunk = connection.recv(1024)
                    if not chunk:
                        break
                    data += chunk
                response = self.dispatch(data.split(b"\n", 1)[0], peer)
                if response:
                    connection.sendall(json.dumps(response).encode() + b"\n")
        except (OSError, ValueError, TypeError, PermissionError, RuntimeError) as exc:
            self.log("control request rejected: %s" % exc)
        finally:
            self._clients.release()

    def _udp(self, sock):
        while not self._stop.is_set():
            try:
                data, peer = sock.recvfrom(8193)
                response = self.dispatch(data, peer[0])
                if response:
                    sock.sendto(json.dumps(response).encode(), peer)
            except socket.timeout:
                continue
            except (OSError, ValueError, TypeError, PermissionError, RuntimeError):
                if self._stop.is_set():
                    return

    def stop(self):
        self._stop.set()
        for sock in self._sockets:
            sock.close()
        self._sockets.clear()
        for thread in self._threads:
            if thread is not threading.current_thread():
                thread.join(timeout=1)
        self._threads.clear()
        self.tcp_address = None
