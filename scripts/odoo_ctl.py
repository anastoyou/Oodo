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
import zipfile
from contextlib import suppress
from pathlib import Path

import psutil
import psycopg2
from psycopg2 import sql

ROOT = Path(__file__).resolve().parent.parent
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def load_env(root: Path = ROOT) -> dict[str, str]:
    """Read database, server, and MCP defaults from the single project .env file."""
    cfg = {
        "DB_HOST": "localhost",
        "DB_PORT": "5432",
        "DB_USER": "postgres",
        "DB_PASSWORD": "postgres",
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
    for key in list(cfg.keys()) + ["ODOO_ENV", "ODOO_WORKERS", "ODOO_CRON_THREADS", "ODOO_LIMIT_TIME_CPU", "ODOO_LIMIT_TIME_REAL"]:
        if key in os.environ and os.environ[key] != "":
            cfg[key] = os.environ[key]
    return cfg


def is_port_open(host: str, port: int) -> bool:
    """Return True if a TCP service accepts connections on host:port."""
    target = "127.0.0.1" if host == "localhost" else host
    with socket.socket() as sock:
        sock.settimeout(1.0)
        return sock.connect_ex((target, port)) == 0


def ensure_postgres(_root: Path, cfg: dict[str, str]) -> None:
    """Verify PostgreSQL is already reachable on DB_HOST:DB_PORT without managing Docker."""
    host = cfg["DB_HOST"]
    port = int(cfg["DB_PORT"])
    print("=" * 56)
    print(f"Checking PostgreSQL status on {host}:{port}...")
    print("=" * 56)
    if is_port_open(host, port):
        return

    raise RuntimeError(
        f"PostgreSQL is not reachable at {host}:{port}. "
        "Start your PostgreSQL server / Docker container manually first (e.g. `docker compose up -d`)."
    )


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


def _is_module_dir(path: Path) -> bool:
    return path.is_dir() and ((path / "__manifest__.py").is_file() or (path / "__openerp__.py").is_file())


def discover_addons_paths(root: Path) -> list[Path]:
    """Return ordered addons_path entries: core odoo/addons first, then addons/ and nested OCA repos."""
    paths: list[Path] = []
    core_addons = root / "odoo" / "addons"
    if core_addons.is_dir():
        paths.append(core_addons)

    custom_root = root / "addons"
    if not custom_root.is_dir():
        return paths

    candidates = [custom_root]
    for entry in sorted(custom_root.iterdir()):
        if not entry.is_dir() or entry.name.startswith(".") or _is_module_dir(entry):
            continue
        if any(_is_module_dir(sub) for sub in entry.iterdir()):
            candidates.append(entry)
        else:
            for nested in sorted(entry.iterdir()):
                if nested.is_dir() and not nested.name.startswith(".") and any(_is_module_dir(sub) for sub in nested.iterdir()):
                    candidates.append(nested)

    seen = {p.resolve() for p in paths}
    for cand in candidates:
        resolved = cand.resolve()
        if resolved not in seen and any(_is_module_dir(sub) for sub in cand.iterdir()):
            paths.append(cand)
            seen.add(resolved)
    return paths


def discover_custom_modules(root: Path) -> list[str]:
    """Return technical names of custom modules located outside odoo/ under addons/."""
    names: list[str] = []
    for addons_dir in discover_addons_paths(root):
        if addons_dir.resolve() == (root / "odoo" / "addons").resolve():
            continue
        for entry in sorted(addons_dir.iterdir()):
            if _is_module_dir(entry) and entry.name not in names:
                names.append(entry.name)
    return names


def write_runtime_conf(root: Path, cfg: dict[str, str], prod: bool | None = None) -> Path:
    """Generate data/odoo.runtime.conf by merging structural odoo.conf with .env DB settings."""
    parser = configparser.ConfigParser(interpolation=None)
    base_conf = root / "odoo.conf"
    if base_conf.is_file():
        parser.read(base_conf, encoding="utf-8")
    if "options" not in parser:
        parser["options"] = {}

    is_prod = prod if prod is not None else cfg.get("ODOO_ENV", "").lower() == "production"
    opts = parser["options"]
    opts["admin_passwd"] = cfg["ADMIN_PASSWORD"]
    opts["db_host"] = cfg["DB_HOST"]
    opts["db_port"] = cfg["DB_PORT"]
    opts["db_user"] = cfg["DB_USER"]
    opts["db_password"] = cfg["DB_PASSWORD"]
    opts["http_port"] = cfg["ODOO_PORT"]
    opts["data_dir"] = str(root / "data")

    discovered = discover_addons_paths(root)
    if discovered:
        opts["addons_path"] = ",".join(str(p) for p in discovered)

    if is_prod:
        opts["list_db"] = "False"
        opts["proxy_mode"] = "True"
        opts["log_level"] = "warn"
        opts["without_demo"] = "all"
        if os.name != "nt":
            opts["workers"] = cfg.get("ODOO_WORKERS", "2")
            opts["max_cron_threads"] = cfg.get("ODOO_CRON_THREADS", "1")
            opts["limit_time_cpu"] = cfg.get("ODOO_LIMIT_TIME_CPU", "120")
            opts["limit_time_real"] = cfg.get("ODOO_LIMIT_TIME_REAL", "240")

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


def _resolve_pg_container(cfg: dict[str, str]) -> str | None:
    """Return a running local Docker container publishing DB_PORT, if any."""
    if cfg["DB_HOST"].lower() not in LOCAL_HOSTS or not shutil.which("docker"):
        return None
    explicit = cfg.get("DB_CONTAINER", "").strip()
    candidates = [explicit] if explicit else []
    res = subprocess.run(
        ["docker", "ps", "--filter", f"publish={cfg['DB_PORT']}", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode == 0:
        candidates.extend(line.strip() for line in res.stdout.splitlines() if line.strip())
    candidates.extend(["shared-postgres", "postgres", "odoo-db"])

    seen: set[str] = set()
    for name in candidates:
        if not name or name in seen:
            continue
        seen.add(name)
        chk = subprocess.run(
            ["docker", "ps", "--filter", f"name=^/{name}$", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            check=False,
        )
        if chk.returncode == 0 and name in chk.stdout.splitlines():
            return name
    return None


def _docker_target_host(host: str) -> str:
    return "host.docker.internal" if host.lower() in LOCAL_HOSTS else host


def _dump_sql_via_pg(cfg: dict[str, str], db_name: str, out_sql: Path) -> None:
    container = _resolve_pg_container(cfg)
    if container:
        container_sql = "/tmp/odoo_save.sql"
        try:
            subprocess.run(
                [
                    "docker",
                    "exec",
                    "-e",
                    f"PGPASSWORD={cfg['DB_PASSWORD']}",
                    container,
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
            subprocess.run(["docker", "cp", f"{container}:{container_sql}", str(out_sql)], check=True)
        finally:
            subprocess.run(
                ["docker", "exec", container, "rm", "-f", container_sql],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        return

    pg_dump_bin = shutil.which("pg_dump")
    if pg_dump_bin:
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

    docker_bin = shutil.which("docker")
    if not docker_bin:
        raise RuntimeError("Neither pg_dump nor Docker was found to dump the PostgreSQL database.")
    with out_sql.open("wb") as fh:
        subprocess.run(
            [
                docker_bin,
                "run",
                "--rm",
                "-e",
                f"PGPASSWORD={cfg['DB_PASSWORD']}",
                "postgres:16-alpine",
                "pg_dump",
                "-h",
                _docker_target_host(cfg["DB_HOST"]),
                "-p",
                cfg["DB_PORT"],
                "-U",
                cfg["DB_USER"],
                "--no-owner",
                db_name,
            ],
            stdout=fh,
            check=True,
        )


def _restore_sql_via_pg(cfg: dict[str, str], target_db: str, dump_sql: Path) -> None:
    container = _resolve_pg_container(cfg)
    if container:
        container_sql = "/tmp/odoo_load.sql"
        try:
            subprocess.run(["docker", "cp", str(dump_sql), f"{container}:{container_sql}"], check=True)
            subprocess.run(
                [
                    "docker",
                    "exec",
                    "-e",
                    f"PGPASSWORD={cfg['DB_PASSWORD']}",
                    container,
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
                ["docker", "exec", container, "rm", "-f", container_sql],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        return

    psql_bin = shutil.which("psql")
    if psql_bin:
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

    docker_bin = shutil.which("docker")
    if not docker_bin:
        raise RuntimeError("Neither psql nor Docker was found to restore the PostgreSQL database.")
    with dump_sql.open("rb") as fh:
        subprocess.run(
            [
                docker_bin,
                "run",
                "--rm",
                "-i",
                "-e",
                f"PGPASSWORD={cfg['DB_PASSWORD']}",
                "postgres:16-alpine",
                "psql",
                "-h",
                _docker_target_host(cfg["DB_HOST"]),
                "-p",
                cfg["DB_PORT"],
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                cfg["DB_USER"],
                "-d",
                target_db,
                "-q",
            ],
            stdin=fh,
            stdout=subprocess.DEVNULL,
            check=True,
        )


def _save_backup_archive(root: Path, cfg: dict[str, str], db_name: str, out_zip: Path) -> bool:
    """Dump database SQL + manifest.json + filestore into out_zip atomically. Returns has_filestore."""
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".tmp_save_", dir=out_zip.parent) as tmp:
        stage = Path(tmp)
        _dump_sql_via_pg(cfg, db_name, stage / "dump.sql")
        manifest = build_manifest(root, cfg, db_name)
        (stage / "manifest.json").write_text(json.dumps(manifest, indent=4), encoding="utf-8")

        filestore_src = root / "data" / "filestore" / db_name
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
    return has_filestore


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
    out_zip = Path(args.output).resolve() if args.output else backups_dir / f"{db_name}_{stamp}.zip"

    print(f'\nSaving database "{db_name}" (SQL + manifest + filestore)...')
    has_filestore = _save_backup_archive(ROOT, cfg, db_name, out_zip)
    size_mb = out_zip.stat().st_size / (1024 * 1024)
    print(f"[SUCCESS] Saved backup: {out_zip} ({size_mb:.2f} MB, filestore={'yes' if has_filestore else 'none'})")
    return 0


def cmd_upgrade(args: argparse.Namespace) -> int:
    """Safely back up DB, pull upstream odoo/ updates without core conflicts, and upgrade custom addons."""
    cfg = load_env(ROOT)
    odoo_dir = ROOT / "odoo"
    odoo_bin = odoo_dir / "odoo-bin"
    if not odoo_bin.is_file():
        raise RuntimeError(f"Odoo source not found at {odoo_bin}")

    if not args.skip_pull:
        dirty = subprocess.run(
            ["git", "-C", str(odoo_dir), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        )
        if dirty.stdout.strip():
            raise RuntimeError(f"Upstream {odoo_dir} has uncommitted local edits; aborting pull to keep core clean.")
        print(f"Pulling latest upstream Odoo ({cfg.get('ODOO_BRANCH', '20.0')}) in {odoo_dir}...")
        subprocess.run(["git", "-C", str(odoo_dir), "pull", "--ff-only"], check=True)

    ensure_postgres(ROOT, cfg)
    avail = list_user_databases(cfg)
    db_name = args.database or (cfg["ODOO_DB"] if cfg["ODOO_DB"] in avail else (avail[0] if avail else ""))
    if not db_name or db_name not in avail:
        raise RuntimeError(f'Target database "{db_name}" not found. Available: {", ".join(avail)}')

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    pre_zip = ROOT / "backups" / f"{db_name}_pre_upgrade_{stamp}.zip"
    print(f'Creating safety backup "{pre_zip.name}" before upgrading...')
    _save_backup_archive(ROOT, cfg, db_name, pre_zip)

    if args.modules:
        custom_mods = [m.strip() for m in args.modules.split(",") if m.strip()]
    else:
        custom_mods = discover_custom_modules(ROOT)
        if not args.install:
            with connect_pg(cfg, db_name) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT name FROM ir_module_module WHERE state = 'installed'")
                    installed = {row[0] for row in cur.fetchall()}
            installed_custom = [m for m in custom_mods if m in installed]
            if installed_custom:
                custom_mods = installed_custom
    if not custom_mods:
        raise RuntimeError("No custom modules found in addons/.")

    stop_local_odoo()
    runtime_conf = write_runtime_conf(ROOT, cfg, prod=True if args.prod else None)
    flag = "-i" if args.install else "-u"
    mod_arg = ",".join(custom_mods)
    print(f'Running Odoo {flag} {mod_arg} on database "{db_name}"...')
    rc = subprocess.run(
        [sys.executable, str(odoo_bin), "-c", str(runtime_conf), "-d", db_name, flag, mod_arg, "--stop-after-init", "--no-http"],
        cwd=ROOT,
    ).returncode
    if rc == 0:
        print(f'\n[SUCCESS] Upgraded {", ".join(custom_mods)} on "{db_name}". Pre-upgrade backup: {pre_zip}')
    return rc


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
        print("You can now start Odoo manually (e.g. .venv\\Scripts\\python.exe odoo\\odoo-bin -c odoo.conf).")
        print("=" * 56)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Odoo backup, restore, and upgrade controller (.env single source of truth)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_upgrade = sub.add_parser("upgrade", help="Back up DB, pull odoo/, and upgrade addons/ modules")
    p_upgrade.add_argument("-d", "--database", help="Target database name (defaults to ODOO_DB)")
    p_upgrade.add_argument("-m", "--modules", help="Comma-separated modules (defaults to all addons/ modules)")
    p_upgrade.add_argument("-i", "--install", action="store_true", help="Install (-i) instead of upgrade (-u)")
    p_upgrade.add_argument("--skip-pull", action="store_true", help="Skip git pull inside odoo/")
    p_upgrade.add_argument("--prod", action="store_true", help="Use production runtime conf")
    p_upgrade.set_defaults(func=cmd_upgrade, pause=False)

    p_save = sub.add_parser("save", help="Save database + filestore backup zip")
    p_save.add_argument("database", nargs="?", help="Database name to back up")
    p_save.add_argument("output", nargs="?", help="Output .zip path (optional)")
    p_save.set_defaults(func=cmd_save)

    p_load = sub.add_parser("load", help="Restore database + filestore backup")
    p_load.add_argument("backup_file", nargs="?", help="Path to .zip or .sql backup")
    p_load.add_argument("database", nargs="?", help="Target database name")
    p_load.add_argument("-y", "--yes", "-f", "--force", action="store_true", help="Overwrite without prompting")
    p_load.set_defaults(func=cmd_load)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    should_pause = False
    if args.command == "save":
        should_pause = args.database is None
    elif args.command == "load":
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

