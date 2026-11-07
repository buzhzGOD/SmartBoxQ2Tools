from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
from typing import Iterable


class AdbError(RuntimeError):
    pass


@dataclass(frozen=True)
class CommandResult:
    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


class AdbClient:
    def __init__(self, executable: str | None = None, timeout: int = 20) -> None:
        resolved = executable or shutil.which("adb")
        if not resolved:
            raise AdbError(
                "adb не найден. Установите Android SDK Platform Tools и добавьте adb в PATH, "
                "либо передайте --adb-path."
            )
        self.executable = str(Path(resolved))
        if executable and not Path(self.executable).is_file():
            raise AdbError(f"Указанный --adb-path не существует или не является файлом: {self.executable}")
        self.timeout = timeout

    def run(self, args: Iterable[str], *, check: bool = True) -> CommandResult:
        command = [self.executable, *args]
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout,
                shell=False,
            )
        except subprocess.TimeoutExpired as error:
            raise AdbError(f"ADB-команда превысила лимит {self.timeout} с: {' '.join(command)}") from error
        result = CommandResult(
            tuple(command), completed.returncode, completed.stdout.strip(), completed.stderr.strip()
        )
        if check and result.returncode:
            detail = result.stderr or result.stdout or "без дополнительного вывода"
            raise AdbError(f"ADB-команда завершилась с кодом {result.returncode}: {detail}")
        return result

    def version(self) -> str:
        return self.run(["version"]).stdout

    def devices(self) -> list[dict[str, str]]:
        output = self.run(["devices", "-l"]).stdout
        devices: list[dict[str, str]] = []
        for line in output.splitlines()[1:]:
            fields = line.split()
            if len(fields) < 2:
                continue
            item = {"serial": fields[0], "state": fields[1]}
            item.update(field.split(":", 1) for field in fields[2:] if ":" in field)
            devices.append(item)
        return devices

    def require_device(self, serial: str) -> None:
        device = next((item for item in self.devices() if item["serial"] == serial), None)
        if not device:
            raise AdbError(f"Устройство {serial!r} не найдено. Используйте команду devices.")
        if device["state"] != "device":
            raise AdbError(
                f"Устройство {serial!r} имеет состояние {device['state']!r}; "
                "подтвердите RSA-ключ и восстановите подключение перед изменениями."
            )

    def serial_run(self, serial: str, args: Iterable[str], *, check: bool = True) -> CommandResult:
        return self.run(["-s", serial, *args], check=check)

    def shell(self, serial: str, *args: str, check: bool = True) -> CommandResult:
        return self.serial_run(serial, ["shell", *args], check=check)

    def install(self, serial: str, apk: Path) -> CommandResult:
        return self.serial_run(serial, ["install", "-r", str(apk)])
