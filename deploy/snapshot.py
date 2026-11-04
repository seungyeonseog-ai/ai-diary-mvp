"""중지된 배포 데이터의 해시 포함 백업·빈 볼륨 복원. 비밀 환경파일 제외."""
import argparse
from contextlib import closing
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import tarfile
import tempfile

PARTS = ("app", "chroma", "redis", "beat")


def digest(stream):
    value = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        value.update(chunk)
    return value.hexdigest()


def create(root, output):
    root, output = Path(root), Path(output)
    if output.exists():
        raise FileExistsError("Backup already exists")
    if not (root / "app/app.db").is_file():
        raise RuntimeError("Application database missing")
    with closing(sqlite3.connect((root / "app/app.db").as_uri()+"?mode=ro", uri=True)) as db:
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise RuntimeError("Database integrity check failed")
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = {}
    # 복원이 거부해야 할 미완성 파일을 완성된 백업 이름으로 노출하지 않는다.
    partial = output.with_suffix(output.suffix + ".partial")
    with partial.open("xb") as archive_file:
        if os.name != "nt": os.chmod(partial, 0o600)
        with tarfile.open(fileobj=archive_file, mode="w:gz") as archive:
            for part in PARTS:
                for path in sorted((root / part).rglob("*")):
                    if path.is_symlink():
                        raise ValueError("Symlinks are not supported in data backups")
                    if not path.is_file(): continue
                    name = path.relative_to(root).as_posix()
                    with path.open("rb") as stream:
                        manifest[name] = {"sha256":digest(stream), "size":path.stat().st_size}
                    archive.add(path, arcname=name, recursive=False)
            data = json.dumps({"version":1,"files":manifest},sort_keys=True).encode()
            info = tarfile.TarInfo("manifest.json")
            info.size, info.mode = len(data), 0o600
            archive.addfile(info, io.BytesIO(data))
    partial.replace(output)
    return {"files":len(manifest), "bytes":output.stat().st_size}


def restore(root, source):
    root, source = Path(root), Path(source)
    for part in PARTS:
        target = root / part
        if target.exists() and any(target.iterdir()):
            raise RuntimeError("Restore requires entirely empty destination volumes")
    with tarfile.open(source, "r:gz") as archive, tempfile.TemporaryDirectory() as temp:
        members = archive.getmembers()
        names = [m.name for m in members]
        if len(names) != len(set(names)) or names.count("manifest.json") != 1:
            raise ValueError("Duplicate or missing archive entries")
        manifest = json.load(archive.extractfile("manifest.json"))
        if manifest.get("version") != 1 or set(names) != set(manifest["files"]) | {"manifest.json"}:
            raise ValueError("Invalid backup manifest")
        for member in members:
            name = PurePosixPath(member.name)
            if (not member.isfile() or name.is_absolute() or ".." in name.parts or
                "\\" in member.name or ":" in member.name or
                (member.name != "manifest.json" and name.parts[0] not in PARTS)):
                raise ValueError("Unsafe archive entry")
            if member.name != "manifest.json":
                expected = manifest["files"][member.name]
                if member.size != expected["size"] or digest(archive.extractfile(member)) != expected["sha256"]:
                    raise ValueError("Backup hash mismatch")
        if "app/app.db" not in manifest["files"]:
            raise ValueError("Application database missing from backup")
        archive.extractall(temp, filter="data")
        with closing(sqlite3.connect((Path(temp)/"app/app.db").as_uri()+"?mode=ro",uri=True)) as db:
            if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError("Restored database integrity check failed")
        for part in PARTS:
            target = root / part
            target.mkdir(parents=True, exist_ok=True)
            if (Path(temp)/part).exists():
                shutil.copytree(Path(temp)/part,target,dirs_exist_ok=True)
            if os.name != "nt" and part != "redis":
                for path in [target, *target.rglob("*")]: os.chown(path,10001,10001)
    return {"files":len(manifest["files"]),"restored":True}


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=["backup","restore"])
    parser.add_argument("archive",type=Path)
    parser.add_argument("--root",type=Path,default=Path("/snapshot"))
    args=parser.parse_args()
    print(json.dumps((create if args.action=="backup" else restore)(args.root,args.archive)))
