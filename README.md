# TeleFlow

**TeleFlow** — десктопное приложение для автоматизированной рассылки сообщений через аккаунты Telegram. Работает через MTProto API (Telethon) — с обычными аккаунтами, не ботами.

> ⚠️ **Важно:** используйте приложение ответственно и в соответствии с [Правилами использования Telegram](https://telegram.org/tos). Массовый спам нарушает правила сервиса.

---

## Возможности

- **Мультиаккаунт** — до 5 аккаунтов Telegram одновременно, быстрое переключение
- **Шаблоны сообщений** — создавайте, редактируйте и переиспользуйте шаблоны с форматированием (жирный, курсив, подчёркивание, зачёркнутый, моноширинный)
- **Медиавложения** — до 10 файлов на шаблон (изображения, видео, аудио, документы)
- **Гибкий планировщик** — 5 режимов расписания:
  - Один раз — конкретная дата и время
  - Ежедневно — в заданное время
  - По дням недели — выбор дней + время
  - С интервалом — каждые N минут/часов
  - Случайное окно — в случайное время в заданном диапазоне
- **Менеджер расписаний** — просмотр, редактирование, пауза и удаление активных расписаний
- **Окно управления отправкой** — единое место для назначения чатов и управления расписаниями
- **CSV импорт** — импорт чатов и шаблонов сообщений из CSV-файлов
- **Безопасность** — сессии шифруются через Fernet + PBKDF2 с уникальной солью; опциональный пароль приложения (bcrypt)
- **Темы** — Dark и Light в стиле Telegram, переключение без перезапуска
- **Локализация** — русский и английский интерфейс

---

## Системные требования

| | Минимум |
|---|---|
| **Python** | 3.12+ |
| **ОС** | Linux (X11 / Wayland), Windows 10+ |
| **Менеджер пакетов** | [uv](https://docs.astral.sh/uv/) |

> **Windows:** поддержка заявлена, но основное тестирование проводилось на Linux. Если обнаружите проблемы — [откройте issue](../../issues).

---

## Установка и запуск

### 1. Получите Telegram API credentials

1. Перейдите на [my.telegram.org](https://my.telegram.org) и войдите в аккаунт
2. Откройте раздел **API development tools**
3. Создайте приложение — получите `api_id` и `api_hash`

### 2. Установите uv

```bash
# Linux / macOS
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 3. Клонируйте и запустите

```bash
git clone https://github.com/xvin84/TeleFlow.git
cd TeleFlow
uv sync
uv run python -m teleflow
```

При первом запуске приложение предложит:
1. Установить пароль для защиты данных (опционально)
2. Добавить первый Telegram аккаунт (потребуются `api_id` и `api_hash`)

---

## CSV форматы

### Импорт чатов

```csv
chat_id,chat_name,chat_type,enabled
-1001234567890,My Group,group,true
-1009876543210,My Channel,channel,true
123456789,John Doe,user,true
```

### Импорт шаблонов сообщений

```csv
title,text,media_path
Приветствие,"Добро пожаловать!",""
Акция,"Скидка 50%!","/path/to/banner.jpg"
```

---

## Структура проекта

```
src/teleflow/
├── core/
│   ├── account_manager.py   # Управление аккаунтами
│   ├── chat_manager.py      # Синхронизация и кеш диалогов
│   ├── message_manager.py   # CRUD шаблонов
│   ├── scheduler.py         # APScheduler 4.x (отдельный поток)
│   ├── sender_engine.py     # Отправка с умной стратегией медиа
│   ├── dispatch.py          # Bridge scheduler → main event loop
│   └── storage/db.py        # SQLite / aiosqlite
├── gui/
│   ├── windows/             # Главные окна (dashboard, login, wizard…)
│   └── components/          # Переиспользуемые виджеты
├── i18n/                    # Локализация (ru / en)
└── utils/                   # crypto, logger, qt_helpers, password
```

---

## Разработка

```bash
uv sync                   # Установить все зависимости
uv run ruff check .       # Линтер
uv run mypy src/          # Проверка типов
```

Подробнее — в [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Стек технологий

| Компонент | Библиотека |
|---|---|
| GUI | PyQt6 |
| Async bridge | qasync |
| Telegram API | Telethon (MTProto) |
| Планировщик | APScheduler 4.x |
| База данных | SQLite + aiosqlite |
| Шифрование | cryptography (Fernet) |
| Пароль | bcrypt |
| Логи | loguru |

---

## Лицензия

GNU General Public License v3.0 — см. [LICENSE](LICENSE).

Производные работы должны оставаться открытыми под GPL v3.
