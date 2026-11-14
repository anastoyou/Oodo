"""Unified project controller for Odoo ERP reading all DB and runtime config from .env."""

from __future__ import annotations

import argparse
import configparser
import datetime
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import zipfile
from contextlib import suppress
from pathlib import Path

import psutil
import psycopg2
from psycopg2 import sql

ROOT = Path(__file__).resolve().parent.parent
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
CONTAINER_NAME = "odoo-db"


def load_env(root: Path = ROOT) -> dict[str, str]:
    """Read database, server, and MCP defaults from the single project .env file."""
    cfg = {
        "DB_HOST": "localhost",
        "DB_PORT": "5432",
        "DB_USER": "odoo",
        "DB_PASSWORD": "odoo",
        "ADMIN_PASSWORD": "masteradmin",
        "ODOO_PORT": "8069",
        "ODOO_BRANCH": "20.0",
        "ODOO_DB": "localhost",
    }
    env_file = root / ".env"
    if not env_file.is_file():
        return cfg

    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        if key:
            cfg[key] = val.strip().strip('"').strip("'")
    return cfg


def is_port_open(host: str, port: int) -> bool:
    """Return True if a TCP service accepts connections on host:port."""
    target = "127.0.0.1" if host == "localhost" else host
    with socket.socket() as sock:
        sock.settimeout(1.0)
        return sock.connect_ex((target, port)) == 0


def ensure_postgres(root: Path, cfg: dict[str, str]) -> None:
    """Ensure PostgreSQL is listening, starting the Docker db service when local."""
    host = cfg["DB_HOST"]
    port = int(cfg["DB_PORT"])
    print("=" * 56)
    print(f"Checking PostgreSQL status on {host}:{port}...")
    print("=" * 56)
    if is_port_open(host, port):
        return

    if host.lower() not in LOCAL_HOSTS:
        raise RuntimeError(f"Remote PostgreSQL at {host}:{port} is not reachable.")

    print(f"PostgreSQL is not listening yet. Starting Docker PostgreSQL ({CONTAINER_NAME})...")
    if subprocess.run(["docker", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode != 0:
        raise RuntimeError("Docker Desktop is NOT running! Start Docker Desktop first.")

    subprocess.run(["docker", "compose", "up", "-d", "db"], cwd=root, check=True)
    print(f"Waiting for PostgreSQL on {host}:{port}...")
    for _ in range(30):
        if is_port_open(host, port):
            return
        time.sleep(0.5)
    raise RuntimeError(f"PostgreSQL did not become ready on {host}:{port} in time.")


def connect_pg(cfg: dict[str, str], dbname: str):
    """Open a psycopg2 connection using credentials from .env."""
    return psycopg2.connect(
        host=cfg["DB_HOST"],
        port=int(cfg["DB_PORT"]),
        user=cfg["DB_USER"],
        password=cfg["DB_PASSWORD"],
        dbname=dbname,
    )


def list_user_databases(cfg: dict[str, str]) -> list[str]:
    """Return sorted non-template, non-system databases."""
    with connect_pg(cfg, "postgres") as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT datname FROM pg_database "
                "WHERE NOT datistemplate AND datname != 'postgres' ORDER BY datname"
            )
            return [row[0] for row in cur.fetchall()]


def db_exists(cfg: dict[str, str], db_name: str) -> bool:
    """Return True if db_name exists in PostgreSQL."""
    with connect_pg(cfg, "postgres") as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
            return cur.fetchone() is not None


def stop_local_odoo() -> None:
    """Terminate any running local odoo-bin Python processes."""
    print("Stopping local Odoo process (odoo-bin)...")
    current_pid = os.getpid()
    targets: list[psutil.Process] = []
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            if proc.info["pid"] == current_pid:
                continue
            cmdline = " ".join(proc.info.get("cmdline") or [])
            if "odoo-bin" in cmdline:
                proc.terminate()
                targets.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if targets:
        _, alive = psutil.wait_procs(targets, timeout=3)
        for proc in alive:
            with suppress(psutil.NoSuchProcess, psutil.AccessDenied):
                proc.kill()


def write_runtime_conf(root: Path, cfg: dict[str, str]) -> Path:
    """Generate data/odoo.runtime.conf by merging structural odoo.conf with .env DB settings."""
    parser = configparser.ConfigParser(interpolation=None)
    base_conf = root / "odoo.conf"
    if base_conf.is_file():
        parser.read(base_conf, encoding="utf-8")
    if "options" not in parser:
        parser["options"] = {}

    opts = parser["options"]
    opts["admin_passwd"] = cfg["ADMIN_PASSWORD"]
    opts["db_host"] = cfg["DB_HOST"]
    opts["db_port"] = cfg["DB_PORT"]
    opts["db_user"] = cfg["DB_USER"]
    opts["db_password"] = cfg["DB_PASSWORD"]
    opts["http_port"] = cfg["ODOO_PORT"]

    runtime_conf = root / "data" / "odoo.runtime.conf"
    runtime_conf.parent.mkdir(parents=True, exist_ok=True)
    with runtime_conf.open("w", encoding="utf-8") as fh:
        parser.write(fh)
    return runtime_conf


def read_odoo_release(root: Path) -> dict[str, object]:
    """Read version metadata from cloned Odoo release.py when present."""
    release_file = root / "odoo" / "odoo" / "release.py"
    if not release_file.is_file():
        return {"version": "20.0", "version_info": [20, 0, 0, "final", 0, ""], "major_version": "20.0"}
    ns: dict[str, object] = {}
    exec(release_file.read_text(encoding="utf-8"), ns)
    return {
        "version": str(ns.get("version", "20.0")),
        "version_info": list(ns.get("version_info", (20, 0, 0, "final", 0, ""))),
        "major_version": str(ns.get("major_version", "20.0")),
    }


def build_manifest(root: Path, cfg: dict[str, str], db_name: str) -> dict[str, object]:
    """Create Odoo-compatible manifest.json metadata for a backup archive."""
    with connect_pg(cfg, db_name) as conn:
        pg_version = "%d.%d" % divmod(conn.server_version // 100, 100)
        modules: dict[str, str] = {}
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.ir_module_module') IS NOT NULL")
            if cur.fetchone()[0]:
                cur.execute("SELECT name, latest_version FROM ir_module_module WHERE state = 'installed'")
                modules = dict(cur.fetchall())

    rel = read_odoo_release(root)
    return {
        "odoo_dump": "1",
        "db_name": db_name,
        "version": rel["version"],
        "version_info": rel["version_info"],
        "major_version": rel["major_version"],
        "pg_version": pg_version,
        "modules": modules,
    }


def _dump_sql_via_pg(cfg: dict[str, str], db_name: str, out_sql: Path) -> None:
    pg_dump_bin = shutil.which("pg_dump")
    if pg_dump_bin and cfg["DB_HOST"].lower() not in LOCAL_HOSTS:
        env = {**os.environ, "PGPASSWORD": cfg["DB_PASSWORD"]}
        subprocess.run(
            [
                pg_dump_bin,
                "-h",
                cfg["DB_HOST"],
                "-p",
                cfg["DB_PORT"],
                "-U",
                cfg["DB_USER"],
                "--no-owner",
                "-f",
                str(out_sql),
                db_name,
            ],
            env=env,
            check=True,
        )
        return

    container_sql = "/tmp/odoo_save.sql"
    try:
        subprocess.run(
            [
                "docker",
                "exec",
                "-e",
                f"PGPASSWORD={cfg['DB_PASSWORD']}",
                CONTAINER_NAME,
                "pg_dump",
                "-U",
                cfg["DB_USER"],
                "--no-owner",
                "-f",
                container_sql,
                db_name,
            ],
            check=True,
        )
        subprocess.run(["docker", "cp", f"{CONTAINER_NAME}:{container_sql}", str(out_sql)], check=True)
    finally:
        subprocess.run(
            ["docker", "exec", CONTAINER_NAME, "rm", "-f", container_sql],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def _restore_sql_via_pg(cfg: dict[str, str], target_db: str, dump_sql: Path) -> None:
    psql_bin = shutil.which("psql")
    if psql_bin and cfg["DB_HOST"].lower() not in LOCAL_HOSTS:
        env = {**os.environ, "PGPASSWORD": cfg["DB_PASSWORD"]}
        subprocess.run(
            [
                psql_bin,
                "-h",
                cfg["DB_HOST"],
                "-p",
                cfg["DB_PORT"],
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                cfg["DB_USER"],
                "-d",
                target_db,
                "-q",
                "-f",
                str(dump_sql),
            ],
            env=env,
            stdout=subprocess.DEVNULL,
            check=True,
        )
        return

    container_sql = "/tmp/odoo_load.sql"
    try:
        subprocess.run(["docker", "cp", str(dump_sql), f"{CONTAINER_NAME}:{container_sql}"], check=True)
        subprocess.run(
            [
                "docker",
                "exec",
                "-e",
                f"PGPASSWORD={cfg['DB_PASSWORD']}",
                CONTAINER_NAME,
                "psql",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                cfg["DB_USER"],
                "-d",
                target_db,
                "-q",
                "-f",
                container_sql,
            ],
            stdout=subprocess.DEVNULL,
            check=True,
        )
    finally:
        subprocess.run(
            ["docker", "exec", CONTAINER_NAME, "rm", "-f", container_sql],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def cmd_start(args: argparse.Namespace) -> int:
    """Start PostgreSQL (if local) and launch Odoo using runtime config built from .env."""
    cfg = load_env(ROOT)
    odoo_bin = ROOT / "odoo" / "odoo-bin"
    if not odoo_bin.is_file():
        raise RuntimeError(f"Odoo source not found at {odoo_bin}")

    ensure_postgres(ROOT, cfg)
    extra = list(args.extra)
    if extra and extra[0] == "--":
        extra = extra[1:]

    has_custom_conf = any(a in ("-c", "--config") or a.startswith("--config=") for a in extra)
    cmd = [sys.executable, str(odoo_bin)]
    if not has_custom_conf:
        runtime_conf = write_runtime_conf(ROOT, cfg)
        cmd.extend(["-c", str(runtime_conf)])
    cmd.extend(extra)

    print()
    print("=" * 56)
    print(f"Starting Odoo {cfg.get('ODOO_BRANCH', '20.0')} directly from {ROOT / 'odoo'}")
    print(f"DB: {cfg['DB_USER']}@{cfg['DB_HOST']}:{cfg['DB_PORT']} | URL: http://localhost:{cfg['ODOO_PORT']}")
    print("Press Ctrl+C to stop Odoo")
    print("=" * 56)
    print()

    try:
        return subprocess.run(cmd, cwd=ROOT).returncode
    except KeyboardInterrupt:
        return 0


def cmd_stop(_args: argparse.Namespace) -> int:
    """Stop local Odoo server and pause Docker PostgreSQL."""
    cfg = load_env(ROOT)
    stop_local_odoo()
    if cfg["DB_HOST"].lower() in LOCAL_HOSTS:
        print(f"Stopping PostgreSQL container ({CONTAINER_NAME})...")
        subprocess.run(["docker", "compose", "stop", "db"], cwd=ROOT, check=False)
    print("Odoo ERP stopped.")
    return 0


def cmd_save(args: argparse.Namespace) -> int:
    """Dump an Odoo database and its filestore to backups/<db>_<timestamp>.zip."""
    cfg = load_env(ROOT)
    ensure_postgres(ROOT, cfg)
    avail = list_user_databases(cfg)
    if not avail:
        raise RuntimeError("No user databases found in PostgreSQL.")

    default_db = cfg["ODOO_DB"] if cfg["ODOO_DB"] in avail else avail[0]
    if args.database:
        db_name = args.database
    else:
        print(f"Available databases: {', '.join(avail)}")
        entered = input(f"Database name to save [{default_db}]: ").strip()
        db_name = entered or default_db

    if db_name not in avail:
        raise RuntimeError(f'Database "{db_name}" does not exist. Available: {", ".join(avail)}')

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backups_dir = ROOT / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    out_zip = Path(args.output).resolve() if args.output else backups_dir / f"{db_name}_{stamp}.zip"
    out_zip.parent.mkdir(parents=True, exist_ok=True)

    print(f'\nSaving database "{db_name}" (SQL + manifest + filestore)...')
    with tempfile.TemporaryDirectory(prefix=".tmp_save_", dir=backups_dir) as tmp:
        stage = Path(tmp)
        _dump_sql_via_pg(cfg, db_name, stage / "dump.sql")
        manifest = build_manifest(ROOT, cfg, db_name)
        (stage / "manifest.json").write_text(json.dumps(manifest, indent=4), encoding="utf-8")

        filestore_src = ROOT / "data" / "filestore" / db_name
        has_filestore = filestore_src.is_dir()
        if has_filestore:
            shutil.copytree(filestore_src, stage / "filestore")

        part_zip = out_zip.with_name(out_zip.name + ".part")
        try:
            with zipfile.ZipFile(part_zip, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.write(stage / "dump.sql", "dump.sql")
                zf.write(stage / "manifest.json", "manifest.json")
                if has_filestore:
                    for file_path in sorted((stage / "filestore").rglob("*")):
                        if file_path.is_file():
                            zf.write(file_path, file_path.relative_to(stage).as_posix())
            os.replace(part_zip, out_zip)
        except Exception:
            part_zip.unlink(missing_ok=True)
            raise

    size_mb = out_zip.stat().st_size / (1024 * 1024)
    print(f"[SUCCESS] Saved backup: {out_zip} ({size_mb:.2f} MB, filestore={'yes' if has_filestore else 'none'})")
    return 0


def _pick_backup_interactive(backups_dir: Path) -> Path:
    backups = (
        sorted(
            (p for p in backups_dir.iterdir() if p.is_file() and p.suffix.lower() in (".zip", ".sql")),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if backups_dir.is_dir()
        else []
    )
    print(f'\nAvailable backups in "{backups_dir}":')
    if not backups:
        print("  (none found)")
    else:
        for idx, path in enumerate(backups, start=1):
            size_mb = path.stat().st_size / (1024 * 1024)
            mtime = datetime.datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            print(f"  [{idx}] {path.name}  ({size_mb:.2f} MB, {mtime})")

    prompt = "Enter backup number [1] or file path: " if backups else "Enter path to .zip or .sql backup file: "
    choice = input(f"\n{prompt}").strip().strip('"')
    if not choice and backups:
        return backups[0]
    if choice.isdigit() and 1 <= int(choice) <= len(backups):
        return backups[int(choice) - 1]
    return Path(choice).expanduser().resolve()


def _extract_backup(backup_file: Path, stage: Path, default_db: str) -> str:
    if zipfile.is_zipfile(backup_file):
        with zipfile.ZipFile(backup_file, "r") as zf:
            members = [m for m in zf.namelist() if m in ("dump.sql", "manifest.json") or m.startswith("filestore/")]
            zf.extractall(stage, members)
    else:
        shutil.copy2(backup_file, stage / "dump.sql")

    if not (stage / "dump.sql").is_file():
        raise RuntimeError(f'Backup "{backup_file}" does not contain dump.sql.')

    manifest_file = stage / "manifest.json"
    if manifest_file.is_file():
        return json.loads(manifest_file.read_text(encoding="utf-8")).get("db_name") or default_db
    return default_db


def cmd_load(args: argparse.Namespace) -> int:
    """Restore an Odoo backup (.zip or .sql) and its filestore."""
    cfg = load_env(ROOT)
    ensure_postgres(ROOT, cfg)

    backups_dir = ROOT / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    backup_file = Path(args.backup_file).resolve() if args.backup_file else _pick_backup_interactive(backups_dir)
    if not backup_file.is_file():
        raise RuntimeError(f'Backup file not found: "{backup_file}"')

    with tempfile.TemporaryDirectory(prefix=".tmp_load_", dir=backups_dir) as tmp:
        stage = Path(tmp)
        suggested_db = _extract_backup(backup_file, stage, cfg["ODOO_DB"])

        if args.database:
            target_db = args.database
        elif args.yes:
            target_db = suggested_db
        else:
            entered = input(f"Target database name to restore into [{suggested_db}]: ").strip()
            target_db = entered or suggested_db

        if db_exists(cfg, target_db) and not args.yes:
            print(f'\nWARNING: Database "{target_db}" and its filestore already exist and will be REPLACED!')
            if input(f'Continue and overwrite "{target_db}"? (Y/N): ').strip().lower() != "y":
                print("Operation cancelled.")
                return 0

        print()
        print("=" * 56)
        stop_local_odoo()
        print(f'Recreating PostgreSQL database "{target_db}"...')
        conn = connect_pg(cfg, "postgres")
        try:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()",
                    (target_db,),
                )
                cur.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(target_db)))
                cur.execute(
                    sql.SQL("CREATE DATABASE {} ENCODING 'unicode' LC_COLLATE 'C' TEMPLATE template0").format(
                        sql.Identifier(target_db)
                    )
                )
        finally:
            conn.close()

        print(f'Restoring SQL dump into "{target_db}"...')
        _restore_sql_via_pg(cfg, target_db, stage / "dump.sql")

        filestore_src = stage / "filestore"
        filestore_dst = ROOT / "data" / "filestore" / target_db
        shutil.rmtree(filestore_dst, ignore_errors=True)
        if filestore_src.is_dir():
            filestore_dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(filestore_src), str(filestore_dst))
            fs_msg = f"filestore restored to {filestore_dst}"
        else:
            fs_msg = "SQL only (no filestore in backup)"

        print(f'[SUCCESS] Restored "{backup_file.name}" into "{target_db}" ({fs_msg}).')
        print("Run start.bat to launch Odoo.")
        print("=" * 56)
    return 0


def cmd_reset(args: argparse.Namespace) -> int:
    """Wipe PostgreSQL Docker volume and local Odoo runtime data."""
    cfg = load_env(ROOT)
    if cfg["DB_HOST"].lower() not in LOCAL_HOSTS:
        raise RuntimeError(f"Refusing to reset remote DB host {cfg['DB_HOST']}.")

    if not args.yes:
        print("=" * 56)
        print("WARNING: This will completely erase all databases and filestore data!")
        print("=" * 56)
        if input("Are you sure you want to completely clear the database? (Y/N): ").strip().lower() != "y":
            print("Operation cancelled.")
            return 0

    stop_local_odoo()
    print("Stopping PostgreSQL container and removing database volumes...")
    subprocess.run(["docker", "compose", "down", "-v"], cwd=ROOT, check=True)

    for folder in (ROOT / "data" / "filestore", ROOT / "data" / "sessions"):
        shutil.rmtree(folder, ignore_errors=True)
    (ROOT / "data" / "odoo.runtime.conf").unlink(missing_ok=True)

    print("Starting fresh PostgreSQL container...")
    subprocess.run(["docker", "compose", "up", "-d", "db"], cwd=ROOT, check=True)
    print("\nDatabase has been completely cleared! Run start.bat to open Odoo.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Odoo project controller (.env single source of truth)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_start = sub.add_parser("start", help="Start Odoo using .env DB config")
    p_start.add_argument("extra", nargs=argparse.REMAINDER, help="Arguments passed through to odoo-bin")
    p_start.set_defaults(func=cmd_start, pause=False)

    p_stop = sub.add_parser("stop", help="Stop local Odoo and PostgreSQL container")
    p_stop.add_argument("-y", "--yes", action="store_true", help="Do not pause on exit")
    p_stop.set_defaults(func=cmd_stop)

    p_save = sub.add_parser("save", help="Save database + filestore backup zip")
    p_save.add_argument("database", nargs="?", help="Database name to back up")
    p_save.add_argument("output", nargs="?", help="Output .zip path (optional)")
    p_save.set_defaults(func=cmd_save)

    p_load = sub.add_parser("load", help="Restore database + filestore backup")
    p_load.add_argument("backup_file", nargs="?", help="Path to .zip or .sql backup")
    p_load.add_argument("database", nargs="?", help="Target database name")
    p_load.add_argument("-y", "--yes", "-f", "--force", action="store_true", help="Overwrite without prompting")
    p_load.set_defaults(func=cmd_load)

    p_reset = sub.add_parser("reset", help="Reset local PostgreSQL volume and filestore")
    p_reset.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompt")
    p_reset.set_defaults(func=cmd_reset)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    should_pause = False
    if args.command == "save":
        should_pause = args.database is None
    elif args.command in ("load", "stop", "reset"):
        should_pause = not args.yes

    try:
        return args.func(args)
    except Exception as exc:
        print(f"\n[ERROR] {exc}")
        return 1
    finally:
        if should_pause:
            input("\nPress Enter to exit...")


if __name__ == "__main__":
    sys.exit(main())

