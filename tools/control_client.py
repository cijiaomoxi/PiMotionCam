#!/usr/bin/env python3
"""Signed PiMotionCam control client (secret from PMC_CONTROL_SECRET)."""

import argparse
import json
import os
from pathlib import Path
import socket
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.control import packet, sign_message
import hmac


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", default="")
    parser.add_argument("--message")
    parser.add_argument("--host", default="225.0.0.55")
    parser.add_argument("--port", type=int, default=22555)
    parser.add_argument("--tcp", action="store_true")
    args = parser.parse_args()
    secret = os.environ.get("PMC_CONTROL_SECRET", "")
    if len(secret) < 16:
        parser.error("Set PMC_CONTROL_SECRET (at least 16 characters)")
    body = packet(
        secret,
        args.command,
        kind="pkc-message" if args.message is not None else "command",
        message=args.message or "",
    )
    encoded = json.dumps(body).encode() + b"\n"
    if args.tcp:
        with socket.create_connection((args.host, args.port), timeout=3) as sock:
            sock.sendall(encoded)
            response = sock.makefile("rb").readline(8193)
            responses = [json.loads(response)]
    else:
        responses = []
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
            sock.settimeout(3)
            sock.sendto(encoded, (args.host, args.port))
            while True:
                try:
                    data, peer = sock.recvfrom(8193)
                    message = json.loads(data)
                    if message.get("reply_to") == body["id"] and hmac.compare_digest(
                        str(message.get("signature", "")), sign_message(message, secret)
                    ):
                        responses.append({"peer": peer[0], **message})
                except socket.timeout:
                    break
    for response in responses:
        if response.get("reply_to") != body["id"] or not hmac.compare_digest(
            str(response.get("signature", "")), sign_message(response, secret)
        ):
            raise ValueError("Invalid acknowledgment")
    print(json.dumps(responses, ensure_ascii=False, indent=2))
    return 0 if responses else 1


if __name__ == "__main__":
    sys.exit(main())
