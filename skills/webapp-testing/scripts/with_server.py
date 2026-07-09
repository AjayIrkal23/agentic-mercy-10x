#!/usr/bin/env python3
"""Run a command with one or more local servers and clean them up safely."""

from __future__ import annotations

import argparse
import os
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass
class ServerConfig:
    command: str
    port: int
    ready_url: str | None


def normalize_ready_urls(raw_ready_urls: list[str], server_count: int) -> list[str | None]:
    if not raw_ready_urls:
        return [None] * server_count
    if len(raw_ready_urls) != server_count:
        raise ValueError("Number of --ready-url arguments must be zero or match the number of --server arguments")
    normalized: list[str | None] = []
    for url in raw_ready_urls:
        normalized.append(None if url in {"", "-"} else url)
    return normalized


def is_port_ready(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def is_url_ready(url: str) -> bool:
    request = urllib.request.Request(url, headers={"User-Agent": "webapp-testing/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=2):
            return True
    except urllib.error.HTTPError as exc:
        return 200 <= exc.code < 500
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def wait_for_server(process: subprocess.Popen[bytes], server: ServerConfig, host: str, timeout: int, interval: float) -> None:
    deadline = time.monotonic() + timeout
    readiness_target = server.ready_url or f"{host}:{server.port}"
    while time.monotonic() < deadline:
        exit_code = process.poll()
        if exit_code is not None:
            raise RuntimeError(
                f"Server exited with code {exit_code} before becoming ready: {server.command}"
            )
        ready = is_url_ready(server.ready_url) if server.ready_url else is_port_ready(host, server.port)
        if ready:
            print(f"Ready: {readiness_target}")
            return
        time.sleep(interval)
    raise RuntimeError(f"Timed out waiting for {readiness_target} after {timeout}s")


def terminate_process_tree(process: subprocess.Popen[bytes], grace_period: int) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        process.wait(timeout=grace_period)
    except ProcessLookupError:
        return
    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        process.wait()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Start one or more local servers, wait for readiness, run a command, then clean up."
    )
    parser.add_argument(
        "--server",
        action="append",
        dest="servers",
        required=True,
        help="Server command to run. Repeat for multiple servers.",
    )
    parser.add_argument(
        "--port",
        action="append",
        dest="ports",
        type=int,
        required=True,
        help="Readiness port for each server. Repeat to match --server.",
    )
    parser.add_argument(
        "--ready-url",
        action="append",
        default=[],
        help="Optional readiness URL for each server. Repeat to match --server count, or use '-' to fall back to port polling.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host used for port polling. Default: 127.0.0.1")
    parser.add_argument("--timeout", type=int, default=45, help="Timeout in seconds per server. Default: 45")
    parser.add_argument("--interval", type=float, default=0.5, help="Polling interval in seconds. Default: 0.5")
    parser.add_argument(
        "--quiet-servers",
        action="store_true",
        help="Suppress server stdout and stderr instead of inheriting them.",
    )
    parser.add_argument(
        "--grace-period",
        type=int,
        default=5,
        help="Seconds to wait after SIGTERM before force killing a server. Default: 5",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Command to run after the servers are ready")
    return parser


def parse_server_configs(args: argparse.Namespace) -> list[ServerConfig]:
    if len(args.servers) != len(args.ports):
        raise ValueError("Number of --server and --port arguments must match")
    ready_urls = normalize_ready_urls(args.ready_url, len(args.servers))
    return [
        ServerConfig(command=command, port=port, ready_url=ready_url)
        for command, port, ready_url in zip(args.servers, args.ports, ready_urls)
    ]


def start_server(server: ServerConfig, quiet_servers: bool) -> subprocess.Popen[bytes]:
    stdout_target = subprocess.DEVNULL if quiet_servers else None
    stderr_target = subprocess.DEVNULL if quiet_servers else None
    shell_path = os.environ.get("SHELL") or "/bin/bash"
    return subprocess.Popen(
        [shell_path, "-lc", server.command],
        start_new_session=True,
        stdout=stdout_target,
        stderr=stderr_target,
    )


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("No command specified after server startup")

    try:
        servers = parse_server_configs(args)
    except ValueError as exc:
        parser.error(str(exc))

    processes: list[subprocess.Popen[bytes]] = []
    try:
        for index, server in enumerate(servers, start=1):
            print(f"Starting server {index}/{len(servers)}: {server.command}")
            process = start_server(server, args.quiet_servers)
            processes.append(process)
            print(
                f"Waiting for readiness on "
                f"{server.ready_url if server.ready_url else f'{args.host}:{server.port}'}"
            )
            wait_for_server(process, server, args.host, args.timeout, args.interval)

        print(f"Running command: {' '.join(command)}")
        result = subprocess.run(command, check=False)
        return result.returncode
    finally:
        if processes:
            print(f"Stopping {len(processes)} server(s)...")
        for process in reversed(processes):
            terminate_process_tree(process, args.grace_period)


if __name__ == "__main__":
    raise SystemExit(main())
