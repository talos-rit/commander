import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile

import pytest

spec = importlib.util.spec_from_file_location("pivision_deploy", Path(__file__).parents[2] / "tools/pivision_deploy.py")
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)


def bundle(tmp_path, extra=None, corrupt=False):
    files = {name: b"value = 1\n" for name in
             ("main.py", "controller.py", "control_api.py", "web_server.py", "perception.py")}
    manifest = {"schema_version": 1, "release_id": "20261001T220000Z-12345678",
                "files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
    if corrupt:
        files["main.py"] = b"value = 2\n"
    files["deployment.json"] = json.dumps(manifest).encode()
    if extra:
        files[extra] = b"value = 1\n"
    path = tmp_path / "bundle.tar"
    with tarfile.open(path, "w") as archive:
        for name, data in files.items():
            member = tarfile.TarInfo("./" + name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    return path


def test_verified_bundle_extracts_without_systemd_or_remote_access(tmp_path, monkeypatch):
    monkeypatch.setattr(deploy, "run", lambda *args: pytest.fail("Verification must stay offline"))
    destination = tmp_path / "release"
    manifest = deploy.unpack_bundle(bundle(tmp_path), destination)
    assert manifest["release_id"] == "20261001T220000Z-12345678"
    assert (destination / "main.py").read_bytes() == b"value = 1\n"


@pytest.mark.parametrize("entry", ["../outside.py", "/outside.py", "link/inside.py", "unexpected.py"])
def test_invalid_bundle_rejected_before_creating_release(tmp_path, entry):
    destination = tmp_path / "release"
    with pytest.raises(ValueError):
        deploy.unpack_bundle(bundle(tmp_path, extra=entry), destination)
    assert not destination.exists()


def test_checksum_failure_does_not_install_modified_files(tmp_path):
    destination = tmp_path / "release"
    with pytest.raises(ValueError, match="Checksum mismatch"):
        deploy.unpack_bundle(bundle(tmp_path, corrupt=True), destination)
    assert not destination.exists()
