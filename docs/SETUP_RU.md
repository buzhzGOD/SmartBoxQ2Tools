# Безопасная установка и использование

## 1. Подготовка приставки

1. На Q2 включите режим разработчика и **USB debugging** или **Wireless debugging**.
2. Подключите приставку к ПК по USB либо выполните штатное pairing/`adb connect` с Android Platform Tools.
3. Подтвердите RSA-отпечаток компьютера на экране телевизора.
4. Установите Android SDK Platform Tools и Python 3.12+ на Windows.

Проверка:

```powershell
.\tools\adb-cleaner\smartbox-q2.ps1 doctor
```

```powershell
.\tools\adb-cleaner\smartbox-q2.ps1 devices
```

Если устройств несколько, всегда используйте точный `--serial`. Инструмент не выберет первое найденное устройство.

## 2. Диагностика — обязательный первый шаг

```powershell
.\tools\adb-cleaner\smartbox-q2.ps1 diagnose --serial YOUR_SERIAL
```

Команда создаёт локальный JSON в `device-data/`: Android API, fingerprint, модель, текущий Home, кандидаты Home, активная клавиатура и состояния пакетов. Эти данные не отправляются в сеть.

Не применяйте готовый профиль от другой приставки: даже две Q2 могут иметь разные Android-версии и наборы системных пакетов.

## 3. Установка и проверка launcher

Соберите APK после установки JDK 17+, Android SDK и Gradle 8.9+ (Gradle wrapper появится после первой локальной инициализации Gradle):

```powershell
cd launcher
gradle :app:assembleDebug
```

Проверочная установка не меняет Home:

```powershell
.\tools\adb-cleaner\smartbox-q2.ps1 install-launcher --serial YOUR_SERIAL --apk .\launcher\app\build\outputs\apk\debug\app-debug.apk --apply
```

Откройте приложение через обычный launcher. Проверьте D-pad, запуск приложений, системные настройки, нажатие Home и пункт «Перезагрузить приставку» в меню Back. Лишь затем в меню Q2 Home выберите **Использовать как Home** и подтвердите системный диалог (если прошивка его поддерживает).

Перезагрузка завершает запущенные приложения и перезапускает систему; это не удаляет данные приложений или дисковый кэш. На некоторых прошивках Android не разрешает обычному приложению открыть системный reboot-экран — тогда Q2 Home честно предложит системные Settings. Для полной удалённой перезагрузки через авторизованный ПК используйте:

```powershell
.\.tooling\android-sdk\platform-tools\adb.exe -s YOUR_SERIAL reboot
```

Программа не назначает Home скрытыми OEM-командами и не отключает заводской launcher.

## 4. Профиль и безопасное отключение

Скопируйте [шаблон](../profiles/templates/q2-profile.template.json) в `profiles/user/`, перенесите **точные** значения fingerprint/API/model из диагностики. В `packages` указывайте только вручную проверенные пользовательские приложения из `/data/app`.

Сначала проверьте структуру и dry-run:

```powershell
.\tools\adb-cleaner\smartbox-q2.ps1 profile-validate .\profiles\user\my-q2.json
```

```powershell
.\tools\adb-cleaner\smartbox-q2.ps1 plan --serial YOUR_SERIAL --profile .\profiles\user\my-q2.json
```

`plan` печатает verification token. После проверки передайте его дословно:

```powershell
.\tools\adb-cleaner\smartbox-q2.ps1 apply --serial YOUR_SERIAL --profile .\profiles\user\my-q2.json --apply --token TOKEN_FROM_PLAN
```

До первой операции создаётся бэкап. MVP намеренно блокирует системные/Vendor пакеты, Settings, SystemUI, установщик приложений, Home-обработчики, IME и всё вне `/data/app`.

## 5. Восстановление

Если после применения что-то работает неправильно, не отключайте новые пакеты. Укажите путь к папке бэкапа из вывода:

```powershell
.\tools\adb-cleaner\smartbox-q2.ps1 restore --serial YOUR_SERIAL --backup .\device-data\DEVICE\backups\TIMESTAMP
```

Проверьте список и token, затем повторите с `--apply --token TOKEN_FROM_PLAN`.

Если Home недоступен, подключите ADB и сначала запустите обычный системный выбор Home:

```powershell
.\tools\adb-cleaner\smartbox-q2.ps1 open-home-selector --serial YOUR_SERIAL
```

После обслуживания отключите отладку на Q2 и отзовите авторизованные компьютеры в настройках разработчика.
