from __future__ import annotations

from dataclasses import dataclass
import re


class PolicyError(ValueError):
    pass


EXACT_PROTECTED_PACKAGES = frozenset(
    {
        "android",
        "com.android.systemui",
        "com.android.settings",
        "com.android.permissioncontroller",
        "com.google.android.permissioncontroller",
        "com.android.packageinstaller",
        "com.google.android.packageinstaller",
        "com.android.shell",
        "com.android.adb",
        "com.google.android.gms",
        "com.android.vending",
        "com.google.android.gsf",
    }
)

PROTECTED_NAME_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"(?:^|[._-])(settings|systemui|permissioncontroller|packageinstaller)(?:$|[._-])",
        r"(?:^|[._-])(setupwizard|provision|inputmethod|ime|bluetooth|wifi|network)(?:$|[._-])",
        r"(?:^|[._-])(deviceadmin|devicepolicy|managedprovisioning|ota|updater)(?:$|[._-])",
    )
)


@dataclass(frozen=True)
class PackageFact:
    name: str
    apk_path: str | None
    is_home_handler: bool
    is_current_home: bool
    is_active_ime: bool
    enabled: bool


def protection_reason(fact: PackageFact) -> str | None:
    if fact.name in EXACT_PROTECTED_PACKAGES:
        return "пакет относится к обязательному системному компоненту"
    if fact.is_current_home:
        return "пакет является текущим обработчиком Home"
    if fact.is_home_handler:
        return "пакет зарегистрирован как резервный обработчик Home"
    if fact.is_active_ime:
        return "пакет является активной экранной клавиатурой"
    if not fact.apk_path or not fact.apk_path.startswith("/data/app/"):
        return "MVP разрешает отключать только вручную проверенные пользовательские приложения из /data/app"
    if any(pattern.search(fact.name) for pattern in PROTECTED_NAME_PATTERNS):
        return "имя пакета похоже на защищённую системную роль"
    return None


def assert_safe_target(fact: PackageFact) -> None:
    reason = protection_reason(fact)
    if reason:
        raise PolicyError(f"{fact.name}: {reason}")
    if not fact.enabled:
        raise PolicyError(f"{fact.name}: пакет уже отключён или имеет неизвестное состояние")
