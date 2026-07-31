#!/usr/bin/env bash
# Собирает .dmg для тех, кто не хочет запускать команды в терминале.
#
#   build/make_dmg.sh dist/deru-macos-arm64 dist/deru-macos-x86_64 dist/DesktopExplorerRU.dmg
#
# Внутри образа лежит один файл, который нужно открыть двойным щелчком; он сам
# выбирает сборку под процессор. Приложения спрятаны в подпапку, чтобы игроку
# было очевидно, что запускать.
set -euo pipefail

ARM="${1:?путь к сборке arm64}"
X86="${2:?путь к сборке x86_64}"
OUT="${3:?куда положить .dmg}"

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

VOLUME="Русификатор Desktop Explorer"
ROOT="$STAGE/$VOLUME"
mkdir -p "$ROOT/bin"
cp "$ARM" "$ROOT/bin/deru-macos-arm64"
cp "$X86" "$ROOT/bin/deru-macos-x86_64"
chmod +x "$ROOT/bin/"*

cat > "$ROOT/Русификатор.command" <<'LAUNCHER'
#!/usr/bin/env bash
# Двойной щелчок открывает Terminal и запускает мастер установки.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
case "$(uname -m)" in
  arm64)  BIN="$DIR/bin/deru-macos-arm64" ;;
  x86_64) BIN="$DIR/bin/deru-macos-x86_64" ;;
  *) echo "Неизвестный процессор $(uname -m)"; read -r -p "Enter — выход"; exit 1 ;;
esac
# Файл приехал внутри образа, значит на нём карантин: снимаем копию во
# временную папку, там же её и запускаем — с примонтированного образа
# Gatekeeper запускать не даст.
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
cp "$BIN" "$WORK/deru"
chmod +x "$WORK/deru"
xattr -cr "$WORK/deru" 2>/dev/null || true
codesign -v "$WORK/deru" >/dev/null 2>&1 || codesign --force --sign - "$WORK/deru" >/dev/null 2>&1 || true
"$WORK/deru"
LAUNCHER
chmod +x "$ROOT/Русификатор.command"

cat > "$ROOT/ПРОЧТИ МЕНЯ.txt" <<'READ'
Русификатор Desktop Explorer
============================

Как запустить
-------------
1. Нажмите на «Русификатор.command» ПРАВОЙ кнопкой мыши и выберите «Открыть».
2. В окне с предупреждением нажмите «Открыть» ещё раз.

Именно правой кнопкой: приложение не подписано платным сертификатом Apple,
и при обычном двойном щелчке macOS откажется его запускать. Это разовое
действие — дальше файл открывается как обычно.

Способ без этих плясок — одна команда в Терминале:

  curl -fsSL https://raw.githubusercontent.com/EloWeld/DesktopExplorer-RU/main/install.sh | bash

Что делает русификатор
----------------------
Правит вашу копию игры: добавляет кириллицу в шрифты и подменяет тексты.
Оригиналы сохраняются в папке _ru_backup_original рядом с игрой, откатить
перевод можно в самом мастере (пункт «Удалить русификатор»).

Русский язык занимает место испанского — пятого слота в игре нет.
После обновления игры в Steam перевод слетает: запустите мастер заново.
READ

rm -f "$OUT"
hdiutil create -volname "$VOLUME" -srcfolder "$ROOT" -ov -format UDZO "$OUT"
echo "готово: $OUT"
