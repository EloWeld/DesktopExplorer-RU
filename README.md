# Desktop Explorer — Russian Translation / Русификатор

Unofficial Russian localization for **Desktop Explorer** (Recurring Dream) on Steam.
Неофициальный перевод игры **Desktop Explorer** на русский язык.

**Keywords / Ключевые слова:** Desktop Explorer русификатор · Desktop Explorer перевод на русский ·
Desktop Explorer Russian translation · русская локализация · Russian language mod · Unity localization patch ·
Steam game translation · русификатор игры · fan translation · Addressables bundle patcher

---

## English

### What this is

A patcher that adds a Russian translation to Desktop Explorer. It edits **your own copy**
of the game: fonts and string tables are read from your installation, modified, and written
back. **No game assets are distributed with this tool.**

96% of the readable text is translated — dialogue, chat logs, in-game websites, documents,
UI and credits. The Cyrillic glyphs missing from the game's pixel fonts are taken from
[Ark Pixel](https://github.com/TakWolf/ark-pixel-font) (SIL OFL 1.1), whose 12px grid
matches the game fonts' cap height and x-height exactly. Everything that is deliberately
not translated shows its original **English** text, so every puzzle stays solvable.

### Install

**macOS — one command.** No Python, no dependencies, nothing left behind:

```bash
curl -fsSL https://raw.githubusercontent.com/EloWeld/DesktopExplorer-RU/main/install.sh | bash
```

It downloads the wizard from the latest release, verifies its checksum, runs it
and deletes it afterwards. The wizard finds the game itself — including Steam
libraries on other drives — shows what it is about to do and asks before
touching anything.

**Prefer clicking?** Download `DesktopExplorerRU.dmg` from
[Releases](https://github.com/EloWeld/DesktopExplorer-RU/releases/latest),
open it, then **right-click** `Русификатор.command` → **Open** → **Open**.
Right-click is not optional: the app is not signed with a paid Apple
certificate, and a plain double-click is refused by Gatekeeper. The `curl`
route above avoids that entirely.

**Windows — one command.** Paste this into PowerShell and press Enter:

```powershell
irm https://raw.githubusercontent.com/EloWeld/DesktopExplorer-RU/main/install.ps1 | iex
```

It downloads the wizard from the latest release, verifies its checksum, runs
it and deletes it afterwards. The build is not code-signed, so an antivirus
may grumble about an unknown publisher — the checksum above is what actually
vouches for the file.

Then launch the game — it starts in Russian. If it does not, pick
**Options → Language → Русский язык**.

Linux: run from source for now (see *From source* below).

### Uninstall

Run the wizard again and choose **«Удалить русификатор»**, or from source:

```bash
python3 patch.py --restore
```

Originals are backed up to `_ru_backup_original` next to the game. Steam's
*Verify integrity of game files* restores them too.

### From source

Python 3.9+ required. On Windows the commands are the same, with `python`
instead of `python3`.

```bash
pip install -r requirements.txt
python3 deru.py                  # the wizard
python3 patch.py                 # plain command line, no prompts
python3 patch.py --game "/path/to/Desktop Explorer"
python3 patch.py --status        # is it installed?
python3 patch.py --restore       # undo everything
```

### Read this before installing

- **Russian replaces Spanish.** There is no fifth language slot; adding one would require
  rebuilding the game. Spanish becomes Russian.
- **Game updates wipe the patch.** Re-run the patcher after every Steam update — the
  wizard notices and says so on its first screen.
- **macOS and Windows tested.** Released builds cover macOS (Apple Silicon and
  Intel) and Windows x64; the Windows build is verified by the CI smoke test
  and community reports. On Linux the code detects the platform folder itself
  and should run from source, but it has not been tested there.
- **Asset integrity checks are disabled.** Addressables verifies bundle checksums and
  refuses to load modified files, so the patcher zeroes them in the catalog.

### Deliberately left in English

Translating these would make puzzles unsolvable:

- file names on the desktop — terminal commands reference them literally;
- terminal commands and their parameters — the player types them;
- passwords and accepted input variants — matched against player input;
- internal strings the developers marked `DO NOT LOCALIZE`.

All of these are rebuilt from your own English tables at patch time — they read in
English, never in Spanish, even though the translation lives in the Spanish slot.

The `Windows Monoline` dotted typeface has no Cyrillic of its own; text set in it
falls back to the Regular face where needed.

### Known rough edges

The translation is machine-produced and not proofread by a human, so stylistic
awkwardness is likely. About fifty short UI labels are wider in Russian than in English
(`Copy` → `Копировать`) and may sit close to the edge of their buttons.

The game's own Bold typeface ships a broken Cyrillic **И** — it is a copy of Latin `N`.
The patcher redraws it.

### How it works

- `deru.py` — the wizard: menu, warnings, progress, plain-language errors. Ships as
  the released binary.
- `patch.py` — the same work without prompts, for scripts and for developers.
- `install.sh` — the one-command installer: picks the build for your CPU, checks the
  release checksum, runs the wizard, removes it.
- `install.ps1` — the same one-command installer for Windows (PowerShell).
- `lib/patcher.py` — the patcher: fonts, TMP atlases, strings, catalog. String tables are
  rebuilt as English base + Russian overlay, and the TextMesh Pro atlases are switched
  to readable dynamic multi-atlas mode so new glyphs can be added at runtime.
- `lib/prebake.py` — renders every character the translation uses straight into the
  SDF atlases at patch time. Without this, TMP rasterises each new glyph on the main
  thread the first time it appears — a multi-second freeze on opening any document
  full of fresh Cyrillic.
- `lib/steam.py` — locating the game: default paths plus the library folders Steam
  records in `libraryfolders.vdf`, so an install on a second drive is found too.
- `lib/state.py` — installed, not installed, or wiped by a game update.
- `lib/unityfs.py` — UnityFS bundle reader.
- `lib/writer.py` — byte-faithful bundle writer. Rebuilding an untouched bundle
  reproduces the original file byte for byte.
- `lib/glyphs.py` — the 39 Cyrillic pixel glyphs the native fonts lack, sourced from
  Ark Pixel 12px; the Bold weight is generated by dilating them one pixel, which is
  exactly how the game's own Regular and Bold relate.
- `data/payload.json` — the translation, keyed by string id.
- `translation/desktop_explorer_ru.csv` — the same translation as table/key/text, the form
  the game's own localization pipeline uses.

### For the developers

If you would like to ship Russian officially, `translation/desktop_explorer_ru.csv` is
yours to use. It carries keys and Russian text only — your English source is not
redistributed here. Official support would survive updates and would not cost players
the Spanish locale.

### License

The tooling in this repository is MIT-licensed (see `LICENSE`). The translated text is a
derivative work of the game's script and is published as a fan translation; all rights to
the original writing remain with the game's authors. The Cyrillic glyph shapes in
`lib/glyphs.py` derive from [Ark Pixel](https://github.com/TakWolf/ark-pixel-font)
by TakWolf, used under the SIL Open Font License 1.1.

---

## Русский

### Что это

Патчер, добавляющий в Desktop Explorer русский язык. Он правит **вашу собственную копию**
игры: шрифты и таблицы строк читаются из вашей установки, изменяются и пишутся обратно.
**Файлы игры в комплект не входят.**

Переведено 96% читаемого текста — диалоги, переписка, внутриигровые сайты, документы,
интерфейс и титры. Недостающие кириллические буквы взяты из шрифта
[Ark Pixel](https://github.com/TakWolf/ark-pixel-font) (SIL OFL 1.1) — его 12-пиксельная
сетка совпадает с пропорциями шрифтов игры один в один. Всё, что намеренно не
переведено, показывается **по-английски**, поэтому головоломки остаются проходимыми.

### Установка

**macOS — одна команда.** Ни Python, ни зависимостей, ни следов в системе:

```bash
curl -fsSL https://raw.githubusercontent.com/EloWeld/DesktopExplorer-RU/main/install.sh | bash
```

Скопируйте её в Терминал и нажмите Enter. Команда скачает мастер установки из
последнего релиза, проверит контрольную сумму, запустит — и удалит за собой.
Мастер сам найдёт игру (в том числе в библиотеке Steam на другом диске),
покажет, что собирается сделать, и спросит подтверждение.

**Не любите терминал?** Скачайте `DesktopExplorerRU.dmg` из
[релизов](https://github.com/EloWeld/DesktopExplorer-RU/releases/latest),
откройте образ и нажмите на `Русификатор.command` **правой** кнопкой →
**Открыть** → **Открыть**. Именно правой: приложение не подписано платным
сертификатом Apple, и от обычного двойного щелчка macOS откажется. Команда выше
эту возню обходит.

**Windows — одна команда.** Вставьте её в PowerShell и нажмите Enter:

```powershell
irm https://raw.githubusercontent.com/EloWeld/DesktopExplorer-RU/main/install.ps1 | iex
```

Команда скачает мастер из последнего релиза, проверит контрольную сумму,
запустит — и удалит за собой. Сборка не подписана сертификатом, поэтому
антивирус может ворчать про «неизвестного издателя» — файл поручается именно
контрольной суммой из релиза.

Дальше просто запустите игру — она стартует на русском. Если нет, выберите
**Options → Language → Русский язык**.

Linux: пока только запуском из исходников (см. ниже).

### Удаление

Запустите мастер ещё раз и выберите **«Удалить русификатор»**. Из исходников:

```bash
python3 patch.py --restore
```

Оригиналы сохраняются в папку `_ru_backup_original` рядом с игрой. Их же вернёт
«Проверить целостность файлов» в Steam.

### Из исходников

Нужен Python 3.9 или новее. На Windows команды те же, только `python`
вместо `python3`.

```bash
pip install -r requirements.txt
python3 deru.py                  # мастер
python3 patch.py                 # то же самое без вопросов
python3 patch.py --game "/путь/к/Desktop Explorer"
python3 patch.py --status        # установлен ли перевод
python3 patch.py --restore       # откатить
```

### Прочитайте до установки

- **Русский занимает место испанского.** Пятый языковой слот добавить нельзя без
  пересборки игры, поэтому испанский заменяется русским.
- **Обновление игры затирает перевод.** После каждого обновления в Steam патч надо
  накатывать заново — мастер это замечает и пишет прямо на первом экране.
- **Проверено на macOS и Windows.** Готовые сборки — для macOS (Apple Silicon и
  Intel) и Windows x64; Windows-сборку проверяет смоук-тест в CI и отчёты
  сообщества. На Linux код сам определяет папку платформы и, скорее всего,
  запустится из исходников, но там это не испытывалось.
- **Проверка целостности файлов отключается.** Addressables сверяет контрольные суммы
  бандлов и отказывается грузить изменённые, поэтому патчер обнуляет их в каталоге.

### Намеренно оставлено английским

Перевести это — значит сделать головоломки непроходимыми:

- имена файлов на «рабочем столе» — на них буквально ссылаются команды терминала;
- команды терминала и их параметры — игрок набирает их с клавиатуры;
- пароли и принимаемые варианты ввода — сравниваются с вводом игрока;
- служебные строки, помеченные разработчиками как `DO NOT LOCALIZE`.

Всё это при установке пересобирается из ваших собственных английских таблиц —
такие строки выводятся по-английски и никогда по-испански, хотя перевод и живёт
в испанском слоте.

У точечного начертания `Windows Monoline` своей кириллицы нет — где она нужна,
текст подхватывает обычное начертание.

### Известные шероховатости

Перевод машинный и не вычитан человеком — возможны стилистические огрехи.
Около полусотни коротких подписей по-русски шире английских (`Copy` → «Копировать»)
и местами подходят к краю кнопки вплотную.

В жирном начертании шрифта игры буква **И** изначально нарисована как копия латинской
`N`; патчер её исправляет.

### Как устроено

- `deru.py` — мастер: меню, предупреждения, прогресс, понятные ошибки. Именно он
  собирается в готовое приложение.
- `patch.py` — то же самое без вопросов, для скриптов и разработчиков.
- `install.sh` — установка одной командой: выбирает сборку под процессор, сверяет
  контрольную сумму релиза, запускает мастер и удаляет его за собой.
- `install.ps1` — та же установка одной командой для Windows (PowerShell).
- `lib/patcher.py` — сам патчер: шрифты, атласы TMP, строки, каталог. Таблицы строк
  пересобираются как английская база + русский оверлей, а атласы TextMesh Pro
  переводятся в читаемый динамический multi-atlas режим, чтобы новые глифы
  дорисовывались на лету.
- `lib/prebake.py` — при установке заранее отрисовывает в SDF-атласы все символы,
  которые встречаются в переводе. Без этого TMP растеризует каждый новый глиф в
  главном потоке при первом показе — отсюда многосекундный фриз при открытии
  документа, полного свежей кириллицы.
- `lib/steam.py` — поиск игры: стандартные пути плюс библиотеки, которые Steam
  перечисляет в `libraryfolders.vdf`, — так находится установка на втором диске.
- `lib/state.py` — установлен перевод, не установлен или слетел после обновления игры.
- `lib/unityfs.py` — разборщик бандлов UnityFS.
- `lib/writer.py` — байт-точный сборщик. Пересборка нетронутого бандла даёт файл,
  совпадающий с оригиналом до байта.
- `lib/glyphs.py` — 39 кириллических глифов, которых нет в родных шрифтах, взятые
  из Ark Pixel 12px; жирное начертание выводится утолщением на один пиксель —
  именно так связаны оригинальные шрифты игры.
- `data/payload.json` — перевод, разложенный по идентификаторам строк.
- `translation/desktop_explorer_ru.csv` — тот же перевод в виде таблица/ключ/текст,
  в формате, который понимает конвейер локализации самой игры.

### Разработчикам

Если захотите добавить русский официально — файл `translation/desktop_explorer_ru.csv`
в вашем распоряжении. В нём только ключи и русский текст, английский оригинал здесь
не распространяется. Официальная поддержка пережила бы обновления и не отнимала бы
у игроков испанский язык.

### Лицензия

Код в этом репозитории под лицензией MIT (см. `LICENSE`). Переведённый текст —
производная работа от сценария игры, публикуется как любительский перевод; права на
исходный текст принадлежат авторам игры. Формы кириллических глифов в
`lib/glyphs.py` взяты из шрифта [Ark Pixel](https://github.com/TakWolf/ark-pixel-font)
(автор TakWolf) по лицензии SIL Open Font License 1.1.
