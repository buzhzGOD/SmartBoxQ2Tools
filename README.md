# SmartBoxQ2Tools

Локальный, безопасный набор инструментов для Android TV-приставки Smart Box Q2:

- `launcher/` — лёгкий Android TV Home launcher, рассчитанный на управление пультом;
- `tools/adb-cleaner/` — офлайн CLI для Windows: диагностика ADB, профили, планирование, обратимое отключение пакетов и восстановление;
- `shared/` — схемы форматов и политика защиты критических ролей;
- `docs/` — инструкция по безопасной установке и восстановлению.

## Границы безопасности

Инструмент не требует root, не удаляет APK, данные приложений или прошивку. По умолчанию он только читает состояние устройства. Изменения возможны лишь после явного профиля, dry-run, резервной копии, `--apply` и verification token. В MVP отключаются только вручную проверенные пакеты пользователя из `/data/app`; системные и vendor-пакеты, обработчики Home, активная клавиатура, Settings, SystemUI и компоненты установки всегда заблокированы.

> «Smart Box Q2» не определяет конкретную прошивку. Сначала выполните `diagnose`; не применяйте профиль с другого устройства.

## Быстрый старт Windows

1. Установите [Android SDK Platform Tools](https://developer.android.com/tools/releases/platform-tools), включите USB или Wireless debugging на приставке и подтвердите RSA-ключ на экране.
2. Убедитесь, что Python 3.12+ доступен как `python`.
3. Выполните:

```powershell
python -I tools\adb-cleaner\src\q2_cleaner\cli.py doctor
```

```powershell
python -I tools\adb-cleaner\src\q2_cleaner\cli.py devices
```

```powershell
python -I tools\adb-cleaner\src\q2_cleaner\cli.py diagnose --serial YOUR_SERIAL
```

Подробный безопасный порядок действий — в [docs/SETUP_RU.md](docs/SETUP_RU.md).

## Состояние сборки

В текущей среде не найдены JDK, Android SDK и `adb`, поэтому APK и аппаратная проверка пока не выполнялись. Python-часть не зависит от внешних библиотек.
