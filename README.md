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
UI and credits. The Cyrillic glyphs missing from the game's pixel fonts were drawn to match
its original lettering.

### Install

Python 3.9+ required.

```bash
pip install -r requirements.txt
python3 patch.py
```

The game is found automatically in the default Steam location. Otherwise:

```bash
python3 patch.py --game "/path/to/Desktop Explorer"
```

Then launch the game and pick **Options → Language → Español**.

### Uninstall

```bash
python3 patch.py --restore
```

Originals are backed up to `_ru_backup_original` next to the game. Steam's
*Verify integrity of game files* restores them too.

### Read this before installing

- **Russian replaces Spanish.** There is no fifth language slot; adding one would require
  rebuilding the game. Spanish becomes Russian.
- **Game updates wipe the patch.** Re-run the patcher after every Steam update.
- **macOS tested.** The patcher detects the platform folder itself and should run on
  Windows and Linux, but it has not been tested there.
- **Asset integrity checks are disabled.** Addressables verifies bundle checksums and
  refuses to load modified files, so the patcher zeroes them in the catalog.

### Deliberately left in English

Translating these would make puzzles unsolvable:

- file names on the desktop — terminal commands reference them literally;
- terminal commands and their parameters — the player types them;
- passwords and accepted input variants — matched against player input;
- internal strings the developers marked `DO NOT LOCALIZE`.

The `Windows Monoline` dotted typeface has no Cyrillic; it is used in a handful of places.

### Known rough edges

The translation is machine-produced and not proofread by a human, so stylistic
awkwardness is likely. About fifty short UI labels are wider in Russian than in English
(`Copy` → `Копировать`) and may sit close to the edge of their buttons.

The game's own Bold typeface ships a broken Cyrillic **И** — it is a copy of Latin `N`.
The patcher redraws it.

### How it works

- `patch.py` — the patcher: fonts, strings, catalog.
- `lib/unityfs.py` — UnityFS bundle reader.
- `lib/writer.py` — byte-faithful bundle writer. Rebuilding an untouched bundle
  reproduces the original file byte for byte.
- `lib/glyphs.py` — 39 hand-drawn Cyrillic pixel glyphs; the Bold weight is generated
  by dilating them one pixel, which is exactly how the original fonts relate.
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
the original writing remain with the game's authors.

---

## Русский

### Что это

Патчер, добавляющий в Desktop Explorer русский язык. Он правит **вашу собственную копию**
игры: шрифты и таблицы строк читаются из вашей установки, изменяются и пишутся обратно.
**Файлы игры в комплект не входят.**

Переведено 96% читаемого текста — диалоги, переписка, внутриигровые сайты, документы,
интерфейс и титры. Недостающие кириллические буквы дорисованы в родном пиксельном
стиле игры.

### Установка

Нужен Python 3.9 или новее.

```bash
pip install -r requirements.txt
python3 patch.py
```

Игра ищется автоматически в стандартной папке Steam. Если она в другом месте:

```bash
python3 patch.py --game "/путь/к/Desktop Explorer"
```

Затем запустите игру и выберите **Options → Language → Español**.

### Удаление

```bash
python3 patch.py --restore
```

Оригиналы сохраняются в папку `_ru_backup_original` рядом с игрой. Их же вернёт
«Проверить целостность файлов» в Steam.

### Прочитайте до установки

- **Русский занимает место испанского.** Пятый языковой слот добавить нельзя без
  пересборки игры, поэтому испанский заменяется русским.
- **Обновление игры затирает перевод.** После каждого обновления в Steam патч надо
  накатывать заново.
- **Проверено на macOS.** Патчер сам определяет папку платформы и, скорее всего,
  запустится на Windows и Linux, но там это не испытывалось.
- **Проверка целостности файлов отключается.** Addressables сверяет контрольные суммы
  бандлов и отказывается грузить изменённые, поэтому патчер обнуляет их в каталоге.

### Намеренно оставлено английским

Перевести это — значит сделать головоломки непроходимыми:

- имена файлов на «рабочем столе» — на них буквально ссылаются команды терминала;
- команды терминала и их параметры — игрок набирает их с клавиатуры;
- пароли и принимаемые варианты ввода — сравниваются с вводом игрока;
- служебные строки, помеченные разработчиками как `DO NOT LOCALIZE`.

Точечное начертание `Windows Monoline` осталось без кириллицы, оно используется
в считаных местах.

### Известные шероховатости

Перевод машинный и не вычитан человеком — возможны стилистические огрехи.
Около полусотни коротких подписей по-русски шире английских (`Copy` → «Копировать»)
и местами подходят к краю кнопки вплотную.

В жирном начертании шрифта игры буква **И** изначально нарисована как копия латинской
`N`; патчер её исправляет.

### Как устроено

- `patch.py` — сам патчер: шрифты, строки, каталог.
- `lib/unityfs.py` — разборщик бандлов UnityFS.
- `lib/writer.py` — байт-точный сборщик. Пересборка нетронутого бандла даёт файл,
  совпадающий с оригиналом до байта.
- `lib/glyphs.py` — 39 кириллических пиксельных глифов; жирное начертание выводится
  утолщением на один пиксель — именно так связаны оригинальные шрифты игры.
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
исходный текст принадлежат авторам игры.
