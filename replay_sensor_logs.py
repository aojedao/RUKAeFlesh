"""Replay archived CSV sensor logs into a serial-like stream.

The script reads a log file written by AllSensorReadings.py and re-emits each
row as a single line of "BoardXSensorYS: value" tokens. By default it creates a
temporary PTY and prints the slave device path so AllSensorReadings.py can read
from it without any live hardware.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import os
import pty
import re
import sys
import time
from pathlib import Path


TIMESTAMP_FORMAT = "%H:%M:%S.%f"
KEY_PATTERN = re.compile(r"^B(\d+)S(\d+)([XYZ])$")


def find_default_log() -> Path:
    candidates = sorted(Path.cwd().glob("arduino_readings_*.txt"))
    if not candidates:
        raise FileNotFoundError("No arduino_readings_*.txt file found in the current directory.")
    return candidates[-1]


def parse_timestamp(value: str) -> dt.datetime | None:
    try:
        return dt.datetime.strptime(value.strip(), TIMESTAMP_FORMAT)
    except ValueError:
        return None


def build_serial_line(header: list[str], row: dict[str, str]) -> str:
    tokens: list[str] = []
    for column in header:
        if column == "Timestamp":
            continue
        value = (row.get(column) or "").strip()
        if not value:
            continue
        match = KEY_PATTERN.match(column)
        if not match:
            continue
        board, sensor, axis = match.groups()
        tokens.append(f"Board{board}Sensor{sensor}{axis}: {value}")
    return " ".join(tokens)


def open_output_stream(use_pty: bool, port: str | None, baud_rate: int):
    if use_pty:
        master_fd, slave_fd = pty.openpty()
        slave_path = os.ttyname(slave_fd)
        os.close(slave_fd)
        stream = os.fdopen(master_fd, "w", buffering=1, encoding="utf-8", newline="\n")
        return stream, f"[replay] PTY ready: {slave_path}", None

    if not port:
        raise ValueError("--port is required when --pty is not used.")

    import serial

    serial_port = serial.Serial(port, baud_rate, timeout=1)
    serial_port.reset_output_buffer()
    return serial_port, f"[replay] Writing to serial port: {port} @ {baud_rate}", serial_port


def write_line(stream, line: str) -> None:
    if isinstance(stream, io.TextIOBase):
        stream.write(line + "\n")
        if hasattr(stream, "flush"):
            stream.flush()
        return

    stream.write((line + "\n").encode("utf-8"))
    stream.flush()


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay archived sensor CSV logs.")
    parser.add_argument("--source", type=Path, default=None, help="CSV log file to replay.")
    parser.add_argument("--pty", action="store_true", help="Create a temporary PTY and print its slave path.")
    parser.add_argument("--port", default=None, help="Serial port to write to instead of creating a PTY.")
    parser.add_argument("--baud-rate", type=int, default=115200, help="Baud rate for --port mode.")
    parser.add_argument("--speed", type=float, default=1.0, help="Replay speed multiplier. 1.0 matches the log timing.")
    parser.add_argument("--loop", action="store_true", help="Loop the source file forever.")
    parser.add_argument("--no-timing", action="store_true", help="Ignore timestamps and send rows as fast as possible.")
    args = parser.parse_args()

    source = args.source or find_default_log()
    if not source.exists():
        print(f"[replay] Source file not found: {source}", file=sys.stderr)
        return 1

    stream, status_message, cleanup_target = open_output_stream(args.pty or not args.port, args.port, args.baud_rate)
    print(status_message)
    print(f"[replay] Source: {source}")
    print("[replay] Stop with Ctrl+C.")

    try:
        while True:
            with source.open(newline="") as handle:
                reader = csv.DictReader(handle)
                previous_timestamp = None

                for row in reader:
                    serial_line = build_serial_line(reader.fieldnames or [], row)
                    if not serial_line:
                        continue

                    if not args.no_timing:
                        current_timestamp = parse_timestamp((row.get("Timestamp") or "").strip())
                        if current_timestamp is not None and previous_timestamp is not None:
                            delay_seconds = (current_timestamp - previous_timestamp).total_seconds() / max(args.speed, 1e-9)
                            if delay_seconds > 0:
                                time.sleep(delay_seconds)
                        if current_timestamp is not None:
                            previous_timestamp = current_timestamp

                    write_line(stream, serial_line)

            if not args.loop:
                break

    except KeyboardInterrupt:
        print("\n[replay] Stopped.")
    finally:
        if cleanup_target is not None:
            cleanup_target.close()
        else:
            stream.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())