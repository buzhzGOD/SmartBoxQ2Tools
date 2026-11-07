from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any

from .adb import AdbClient, AdbError
from .policy import PackageFact, PolicyError, assert_safe_target
from .storage import DataError, device_key, digest, read_json, timestamp, verification_token, write_json


PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_DATA_ROOT = PROJECT_ROOT / "device-data"
PROFILE_REQUIRED_KEYS = {"schemaVersion", "profileId", "targetConstraints", "operation", "userId", "packages"}


@dataclass(frozen=True)
class DeviceSnapshot:
    serial: str
    properties: dict[str, str]
    current_home: str | None
    home_packages: frozenset[str]
    active_ime: str | None
    packages: dict[str, dict[str, Any]]

    @property
    def fingerprint(self) -> str:
        return self.properties.get("ro.build.fingerprint", "")


def property_value(adb: AdbClient, serial: str, name: str) -> str:
    return adb.shell(serial, "getprop", name).stdout


def package_from_component(text: str) -> str | None:
    for line in reversed(text.splitlines()):
        candidate = line.strip()
        if "/" in candidate and not candidate.startswith("Warning"):
            return candidate.split("/", 1)[0]
    return None


def package_paths(adb: AdbClient, serial: str) -> dict[str, str]:
    paths: dict[str, str] = {}
    for line in adb.shell(serial, "pm", "list", "packages", "-f", "--user", "0").stdout.splitlines():
        if not line.startswith("package:") or "=" not in line:
            continue
        apk_path, package_name = line.removeprefix("package:").rsplit("=", 1)
        paths[package_name] = apk_path
    return paths


def package_set(adb: AdbClient, serial: str, flag: str) -> set[str]:
    return {
        line.removeprefix("package:")
        for line in adb.shell(serial, "pm", "list", "packages", flag, "--user", "0").stdout.splitlines()
        if line.startswith("package:")
    }


def home_handlers(adb: AdbClient, serial: str) -> set[str]:
    result = adb.shell(
        serial,
        "cmd",
        "package",
        "query-activities",
        "--brief",
        "-a",
        "android.intent.action.MAIN",
        "-c",
        "android.intent.category.HOME",
        check=False,
    )
    handlers = {package_from_component(line) for line in result.stdout.splitlines()}
    return {package for package in handlers if package}


def collect_snapshot(adb: AdbClient, serial: str) -> DeviceSnapshot:
    properties = {
        name: property_value(adb, serial, name)
        for name in (
            "ro.build.version.release",
            "ro.build.version.sdk",
            "ro.build.fingerprint",
            "ro.product.manufacturer",
            "ro.product.model",
            "ro.product.device",
            "ro.board.platform",
            "ro.product.cpu.abi",
        )
    }
    current_home_result = adb.shell(
        serial,
        "cmd",
        "package",
        "resolve-activity",
        "--brief",
        "-a",
        "android.intent.action.MAIN",
        "-c",
        "android.intent.category.HOME",
        check=False,
    )
    current_home = package_from_component(current_home_result.stdout)
    paths = package_paths(adb, serial)
    disabled = package_set(adb, serial, "-d")
    enabled = package_set(adb, serial, "-e")
    active_ime = package_from_component(adb.shell(serial, "settings", "get", "secure", "default_input_method", check=False).stdout)
    handlers = home_handlers(adb, serial)
    packages = {
        name: {
            "apkPath": apk_path,
            "enabled": name in enabled and name not in disabled,
            "disabled": name in disabled,
        }
        for name, apk_path in paths.items()
    }
    return DeviceSnapshot(serial, properties, current_home, frozenset(handlers), active_ime, packages)


def snapshot_json(snapshot: DeviceSnapshot, adb_version: str) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "kind": "smartbox-q2-diagnostic",
        "createdAt": timestamp(),
        "adbVersion": adb_version,
        "serial": snapshot.serial,
        "device": snapshot.properties,
        "currentHomePackage": snapshot.current_home,
        "homePackages": sorted(snapshot.home_packages),
        "activeImePackage": snapshot.active_ime,
        "packages": snapshot.packages,
    }


def load_profile(path: Path) -> dict[str, Any]:
    profile = read_json(path)
    missing = PROFILE_REQUIRED_KEYS - profile.keys()
    if missing:
        raise DataError(f"Профиль не содержит обязательные поля: {', '.join(sorted(missing))}")
    if profile["schemaVersion"] != 1 or profile["operation"] != "disable-user" or profile["userId"] != 0:
        raise DataError("MVP принимает только profile schemaVersion=1, operation=disable-user, userId=0")
    packages = profile["packages"]
    if not isinstance(packages, list) or not packages or not all(isinstance(item, dict) for item in packages):
        raise DataError("packages должен быть непустым списком объектов")
    names = [item.get("package") for item in packages]
    if not all(isinstance(name, str) and name for name in names) or len(names) != len(set(names)):
        raise DataError("каждая запись packages должна иметь уникальное точное поле package")
    for item in packages:
        if set(item) != {"package", "rationale", "riskLevel"}:
            raise DataError("каждая запись packages должна содержать только package, rationale и riskLevel")
        if not isinstance(item["rationale"], str) or not item["rationale"].strip():
            raise DataError("rationale должен быть непустым текстом")
        if item["riskLevel"] not in {"low", "medium"}:
            raise DataError("riskLevel должен быть low или medium")
    return profile


def validate_constraints(profile: dict[str, Any], snapshot: DeviceSnapshot) -> None:
    expected = profile["targetConstraints"]
    if not isinstance(expected, dict) or not expected:
        raise DataError("targetConstraints должен точно привязывать профиль к диагностированному устройству")
    actual = {
        "fingerprint": snapshot.fingerprint,
        "apiLevel": snapshot.properties.get("ro.build.version.sdk", ""),
        "manufacturer": snapshot.properties.get("ro.product.manufacturer", ""),
        "model": snapshot.properties.get("ro.product.model", ""),
    }
    mismatches = [key for key, value in expected.items() if actual.get(key) != str(value)]
    if mismatches:
        raise PolicyError(f"Профиль не подходит этому устройству: {', '.join(mismatches)}")


def facts_for_profile(profile: dict[str, Any], snapshot: DeviceSnapshot) -> list[PackageFact]:
    facts: list[PackageFact] = []
    for item in profile["packages"]:
        name = item["package"]
        package = snapshot.packages.get(name)
        if not package:
            raise PolicyError(f"{name}: пакет не установлен для пользователя 0")
        facts.append(
            PackageFact(
                name=name,
                apk_path=package["apkPath"],
                is_home_handler=name in snapshot.home_packages,
                is_current_home=name == snapshot.current_home,
                is_active_ime=name == snapshot.active_ime,
                enabled=bool(package["enabled"]),
            )
        )
    return facts


def build_plan(profile: dict[str, Any], snapshot: DeviceSnapshot) -> list[PackageFact]:
    validate_constraints(profile, snapshot)
    facts = facts_for_profile(profile, snapshot)
    for fact in facts:
        assert_safe_target(fact)
    if not snapshot.current_home or not snapshot.home_packages:
        raise PolicyError("не удалось надёжно определить обработчик Home; изменения заблокированы")
    return facts


def backup_path(data_root: Path, snapshot: DeviceSnapshot) -> Path:
    return data_root / device_key(snapshot.serial, snapshot.fingerprint) / "backups" / timestamp()


def create_backup(data_root: Path, profile: dict[str, Any], snapshot: DeviceSnapshot, facts: list[PackageFact]) -> Path:
    path = backup_path(data_root, snapshot)
    manifest = {
        "schemaVersion": 1,
        "kind": "smartbox-q2-backup",
        "createdAt": timestamp(),
        "serial": snapshot.serial,
        "fingerprint": snapshot.fingerprint,
        "profileHash": digest(profile),
        "currentHomePackage": snapshot.current_home,
        "packages": [
            {"package": fact.name, "originalEnabled": fact.enabled, "changed": False} for fact in facts
        ],
    }
    write_json(path / "manifest.json", manifest)
    return path


def print_plan(facts: list[PackageFact], serial: str, profile: dict[str, Any]) -> str:
    profile_hash = digest(profile)
    token = verification_token(serial, profile_hash, len(facts))
    print("План изменений (dry-run):")
    for fact in facts:
        print(f"  disable-user --user 0 {fact.name} ({fact.apk_path})")
    print(f"Verification token: {token}")
    return token


def cmd_doctor(args: argparse.Namespace) -> int:
    adb = AdbClient(args.adb_path)
    print(adb.version())
    return 0


def cmd_devices(args: argparse.Namespace) -> int:
    adb = AdbClient(args.adb_path)
    for item in adb.devices():
        print(f"{item['serial']}\t{item['state']}\t{item.get('model', 'unknown')}")
    return 0


def cmd_diagnose(args: argparse.Namespace) -> int:
    adb = AdbClient(args.adb_path)
    adb.require_device(args.serial)
    snapshot = collect_snapshot(adb, args.serial)
    result = snapshot_json(snapshot, adb.version())
    destination = Path(args.data_root) / device_key(snapshot.serial, snapshot.fingerprint) / "diagnostics" / f"{timestamp()}.json"
    write_json(destination, result)
    print(f"Диагностика сохранена: {destination}")
    print(f"Android: {snapshot.properties.get('ro.build.version.release')} (API {snapshot.properties.get('ro.build.version.sdk')})")
    print(f"Устройство: {snapshot.properties.get('ro.product.manufacturer')} {snapshot.properties.get('ro.product.model')}")
    print(f"Home: {snapshot.current_home or 'не определён'}; candidates: {', '.join(sorted(snapshot.home_packages)) or 'нет'}")
    return 0


def cmd_validate_profile(args: argparse.Namespace) -> int:
    profile = load_profile(Path(args.profile))
    print(f"Профиль {profile['profileId']} корректен; пакетов: {len(profile['packages'])}")
    return 0


def plan_from_args(args: argparse.Namespace) -> tuple[AdbClient, dict[str, Any], DeviceSnapshot, list[PackageFact]]:
    adb = AdbClient(args.adb_path)
    adb.require_device(args.serial)
    profile = load_profile(Path(args.profile))
    snapshot = collect_snapshot(adb, args.serial)
    return adb, profile, snapshot, build_plan(profile, snapshot)


def cmd_plan(args: argparse.Namespace) -> int:
    _, profile, snapshot, facts = plan_from_args(args)
    print_plan(facts, snapshot.serial, profile)
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    adb, profile, snapshot, facts = plan_from_args(args)
    expected_token = print_plan(facts, snapshot.serial, profile)
    if not args.apply:
        print("Изменения не выполнены: добавьте --apply после проверки плана.")
        return 0
    if args.token != expected_token:
        raise PolicyError("Неверный verification token. Выполните plan заново и передайте показанный token.")
    backup = create_backup(Path(args.data_root), profile, snapshot, facts)
    manifest = read_json(backup / "manifest.json")
    for entry, fact in zip(manifest["packages"], facts, strict=True):
        adb.shell(snapshot.serial, "pm", "disable-user", "--user", "0", fact.name)
        refreshed = collect_snapshot(adb, snapshot.serial)
        updated = refreshed.packages.get(fact.name, {})
        if updated.get("enabled", True) or refreshed.current_home != snapshot.current_home or not refreshed.home_packages:
            raise PolicyError(f"После изменения {fact.name} health check не пройден; дальнейшие изменения остановлены")
        entry["changed"] = True
        write_json(backup / "manifest.json", manifest)
    print(f"Изменения завершены. Бэкап для восстановления: {backup}")
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    adb = AdbClient(args.adb_path)
    adb.require_device(args.serial)
    backup = Path(args.backup)
    manifest = read_json(backup / "manifest.json")
    snapshot = collect_snapshot(adb, args.serial)
    if manifest.get("serial") != args.serial or manifest.get("fingerprint") != snapshot.fingerprint:
        raise PolicyError("Бэкап принадлежит другому устройству или прошивке; восстановление заблокировано")
    changed = [item["package"] for item in manifest.get("packages", []) if item.get("changed")]
    if not changed:
        print("В бэкапе нет успешно изменённых пакетов.")
        return 0
    token = verification_token(args.serial, manifest["profileHash"], len(changed))
    print("Будут восстановлены: " + ", ".join(changed))
    print(f"Verification token: {token}")
    if not args.apply:
        print("Восстановление не выполнено: добавьте --apply после проверки списка.")
        return 0
    if args.token != token:
        raise PolicyError("Неверный verification token для восстановления")
    for package in changed:
        adb.shell(args.serial, "pm", "enable", "--user", "0", package)
    print("Восстановление завершено.")
    return 0


def cmd_install_launcher(args: argparse.Namespace) -> int:
    apk = Path(args.apk).resolve()
    if not apk.is_file() or apk.suffix.lower() != ".apk":
        raise DataError("--apk должен указывать на существующий APK")
    adb = AdbClient(args.adb_path)
    adb.require_device(args.serial)
    if not args.apply:
        print(f"Будет установлен: {apk}. Добавьте --apply для выполнения.")
        return 0
    print(adb.install(args.serial, apk).stdout)
    return 0


def cmd_open_home_selector(args: argparse.Namespace) -> int:
    adb = AdbClient(args.adb_path)
    adb.require_device(args.serial)
    print(adb.shell(args.serial, "am", "start", "-a", "android.intent.action.MAIN", "-c", "android.intent.category.HOME").stdout)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Безопасный ADB cleaner для Smart Box Q2")
    parser.add_argument("--adb-path", help="путь к adb.exe")
    parser.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT), help="папка локальных диагностик и бэкапов")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor").set_defaults(handler=cmd_doctor)
    commands.add_parser("devices").set_defaults(handler=cmd_devices)
    diagnose = commands.add_parser("diagnose")
    diagnose.add_argument("--serial", required=True)
    diagnose.set_defaults(handler=cmd_diagnose)
    profile = commands.add_parser("profile-validate")
    profile.add_argument("profile")
    profile.set_defaults(handler=cmd_validate_profile)
    for name, handler in (("plan", cmd_plan), ("apply", cmd_apply)):
        command = commands.add_parser(name)
        command.add_argument("--serial", required=True)
        command.add_argument("--profile", required=True)
        if name == "apply":
            command.add_argument("--apply", action="store_true")
            command.add_argument("--token")
        command.set_defaults(handler=handler)
    restore = commands.add_parser("restore")
    restore.add_argument("--serial", required=True)
    restore.add_argument("--backup", required=True)
    restore.add_argument("--apply", action="store_true")
    restore.add_argument("--token")
    restore.set_defaults(handler=cmd_restore)
    install = commands.add_parser("install-launcher")
    install.add_argument("--serial", required=True)
    install.add_argument("--apk", required=True)
    install.add_argument("--apply", action="store_true")
    install.set_defaults(handler=cmd_install_launcher)
    home = commands.add_parser("open-home-selector")
    home.add_argument("--serial", required=True)
    home.set_defaults(handler=cmd_open_home_selector)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except (AdbError, DataError, PolicyError) as error:
        print(f"ОШИБКА: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
