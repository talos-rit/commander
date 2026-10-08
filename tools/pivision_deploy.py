"""Verify a local bundle, or install a versioned PiVision release on Bluey."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile
import time
from urllib.request import urlopen

SERVICE = "pivision-integration.service"
DROPIN = Path("/etc/systemd/system/pivision-integration.service.d/30-release.conf")
PYTHON = "/home/pi/tracker_venv/bin/python"
MODEL = "/home/pi/test/tracker/yolo11n-pose-320.onnx"


def unpack_bundle(bundle, destination):
    with tarfile.open(bundle) as archive:
        members = {}
        for member in archive.getmembers():
            if member.isdir() and member.name in (".", "./"):
                continue
            name = member.name.removeprefix("./")
            if (not member.isfile() or "/" in name or "\\" in name
                    or name in ("", ".", "..") or member.size > 2_000_000
                    or not (name.endswith(".py") or name == "deployment.json") or name in members):
                raise ValueError(f"Unsupported bundle entry: {member.name}")
            members[name] = archive.extractfile(member).read()
        if sum(map(len, members.values())) > 10_000_000:
            raise ValueError("Bundle exceeds size limit")
    manifest = json.loads(members.pop("deployment.json"))
    if manifest.get("schema_version") != 1 or not re.fullmatch(r"\d{8}T\d{6}Z-[a-f0-9]{8}", manifest.get("release_id", "")):
        raise ValueError("Invalid release manifest")
    if set(manifest["files"]) != set(members):
        raise ValueError("Manifest does not match bundle files")
    required = {"main.py", "controller.py", "control_api.py", "web_server.py", "perception.py"}
    if not required <= set(members):
        raise ValueError("Incomplete tracker bundle")
    for name, data in members.items():
        if hashlib.sha256(data).hexdigest() != manifest["files"][name]:
            raise ValueError(f"Checksum mismatch: {name}")
        compile(data, name, "exec")
    destination.mkdir(parents=True, exist_ok=False)
    for name, data in members.items():
        target = destination / name
        target.write_bytes(data)
        target.chmod(0o644)
    (destination / "deployment.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    destination.chmod(0o755)
    return manifest


def run(*arguments):
    result = subprocess.run(arguments, capture_output=True, text=True, timeout=35)
    if result.returncode:
        raise RuntimeError(f"{arguments[0]} failed: {(result.stderr or result.stdout)[-2000:]}")
    return result.stdout.strip()


def wait_ready():
    deadline = time.monotonic() + 25
    error = None
    while time.monotonic() < deadline:
        try:
            with urlopen("http://127.0.0.1:5051/api/v1/control/status", timeout=1) as response:
                status = json.load(response)
            if status.get("enabled") is not False:
                raise RuntimeError("New PiVision service did not start with tracking off")
            return status
        except Exception as failure:
            error = failure
            time.sleep(.25)
    raise RuntimeError(f"PiVision health check failed: {error}")


def apply(bundle, root):
    if sys.platform != "linux" or os.geteuid() != 0:
        raise RuntimeError("Apply must run on the Pi with sudo")
    root = root.resolve()
    if not root.is_relative_to(Path("/home/pi")) or root == Path("/home/pi"):
        raise ValueError("Release root must stay under /home/pi")
    run("systemctl", "cat", SERVICE)  # Existing integration must already be installed.
    if not Path(PYTHON).is_file() or not Path(MODEL).is_file():
        raise RuntimeError("Existing tracker environment/model is missing")
    run(PYTHON, "-c", "import cv2, numpy, onnxruntime, fastapi, uvicorn, loguru")
    with tempfile.TemporaryDirectory(prefix="talos-verify-") as temporary:
        manifest = unpack_bundle(bundle, Path(temporary) / "source")
    release = root / manifest["release_id"]
    unpack_bundle(bundle, release)
    previous = DROPIN.read_bytes() if DROPIN.exists() else None
    override = ("[Service]\n" + f"WorkingDirectory={release}\nExecStart=\n"
                + f"ExecStart={PYTHON} main.py --model {MODEL} --port 5051 --edge-control\n")
    DROPIN.parent.mkdir(parents=True, exist_ok=True)
    pending = DROPIN.with_suffix(".pending")
    pending.write_text(override, encoding="utf-8")
    pending.replace(DROPIN)
    try:
        run("systemctl", "daemon-reload")
        run("systemctl", "restart", SERVICE)
        status = wait_ready()
        run("systemctl", "is-active", SERVICE)
    except Exception as error:
        if previous is None:
            DROPIN.unlink()
        else:
            DROPIN.write_bytes(previous)
        run("systemctl", "daemon-reload")
        run("systemctl", "restart", SERVICE)
        raise RuntimeError(f"Deployment failed; previous PiVision release restored: {error}") from error
    print(json.dumps({"release": str(release), "commander_commit": manifest["commander_commit"],
                      "commander_dirty": manifest.get("commander_dirty", False),
                      "tracking_enabled": status["enabled"], "operator_connected": status["operator_connected"]}))


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check-bundle", type=Path)
    mode.add_argument("--apply", type=Path)
    parser.add_argument("--root", type=Path, default=Path("/home/pi/talos-vision-releases"))
    args = parser.parse_args()
    if args.check_bundle:
        with tempfile.TemporaryDirectory(prefix="talos-verify-") as temporary:
            manifest = unpack_bundle(args.check_bundle, Path(temporary) / "source")
        print(json.dumps({"verified": manifest["release_id"], "files": len(manifest["files"])}))
    else:
        apply(args.apply, args.root)


if __name__ == "__main__":
    main()
