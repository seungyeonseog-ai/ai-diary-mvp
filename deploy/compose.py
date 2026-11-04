"""운영 데이터를 삭제하지 않는 Compose 시작/중지 도구."""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["start", "stop", "check", "build", "backup", "restore"])
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--env-file", default=".env.production")
    parser.add_argument("--project")
    parser.add_argument("--validation", action="store_true")
    args = parser.parse_args()
    env_file = Path(args.env_file).resolve(strict=True)
    # 실제 환경 설정이 출력되는 config 대신 config --quiet만 사용한다.
    cmd = ["docker", "compose", "--project-directory", str(ROOT), "--env-file", str(env_file),
           "-f", str(ROOT / "docker-compose.yml")]
    if args.project:
        cmd += ["--project-name", args.project]
    if args.validation:
        if not args.project or not args.project.startswith("matabus-validation"):
            raise ValueError("Validation requires a separate matabus-validation project")
        cmd += ["-f", str(ROOT / "docker-compose.validation.yml")]
    subprocess.run(["docker", "compose", "version"], check=True)
    subprocess.run(cmd + ["config", "--quiet"], check=True)
    if args.action in ("start", "build"):
        subprocess.run(cmd + ["build", "web"], check=True)
    if args.action == "start":
        # 먼저 기존 서비스를 down 하지 않는다. 준비 실패를 성공으로 출력하지 않는다.
        subprocess.run(cmd + ["up", "-d", "--no-build", "--wait", "--wait-timeout", "900"], check=True)
        print("PASS: service health checks completed")
    elif args.action == "stop":
        subprocess.run(cmd + ["stop"], check=True)
        print("Stopped; containers and all data volumes retained")
    elif args.action == "check":
        subprocess.run(cmd + ["ps"], check=True)
    elif args.action in ("backup", "restore"):
        running = subprocess.check_output(cmd + ["ps", "--status", "running", "--services"], text=True).split()
        if args.action == "restore" and running:
            raise RuntimeError("Restore requires a stopped, separate destination project")
        if args.action == "restore" and args.archive is None:
            raise ValueError("--archive is required")
        default = ROOT / "backups" / ("backup-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")+".tar.gz")
        archive = (args.archive or default).resolve()
        archive.parent.mkdir(parents=True, exist_ok=True)
        if args.action == "backup" and archive.exists(): raise FileExistsError("Backup already exists")
        if args.action == "restore" and not archive.is_file(): raise FileNotFoundError("Backup missing")
        try:
            if running: subprocess.run(cmd + ["stop", *running], check=True)
            subprocess.run(cmd + ["run", "--rm", "--no-deps", "-v", str(archive.parent)+":/backups",
                "maintenance", "python", "-m", "deploy.snapshot", args.action, "/backups/"+archive.name], check=True)
        finally:
            if running: subprocess.run(cmd + ["start", *running], check=True)
        print("PASS: " + args.action + " completed")


if __name__ == "__main__": main()
