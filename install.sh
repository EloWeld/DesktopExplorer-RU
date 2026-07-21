#!/usr/bin/env bash
# Русификатор Desktop Explorer — установка одной командой.
#
#   curl -fsSL https://raw.githubusercontent.com/EloWeld/DesktopExplorer-RU-MacOS/main/install.sh | bash
#
# Скрипт скачивает готовое приложение из последнего релиза, проверяет
# контрольную сумму и запускает мастер. После выхода из мастера файл
# удаляется — в системе ничего не остаётся (DERU_KEEP=1 оставит его).
set -euo pipefail

REPO="EloWeld/DesktopExplorer-RU-MacOS"
BASE="https://github.com/${REPO}/releases/latest/download"

red()  { printf '\033[31m%s\033[0m\n' "$*" >&2; }
dim()  { printf '\033[2m%s\033[0m\n' "$*"; }
bold() { printf '\033[1m%s\033[0m\n' "$*"; }

die() {
  red "Ошибка: $*"
  exit 1
}

[ "$(uname -s)" = "Darwin" ] || die "этот установщик рассчитан на macOS."

case "$(uname -m)" in
  arm64)  ASSET="deru-macos-arm64" ;;
  x86_64) ASSET="deru-macos-x86_64" ;;
  *)      die "неизвестный процессор $(uname -m) — соберите из исходников." ;;
esac

command -v curl >/dev/null 2>&1 || die "не найден curl."

WORK="$(mktemp -d "${TMPDIR:-/tmp}/deru.XXXXXX")"
if [ "${DERU_KEEP:-0}" = "1" ]; then
  trap 'dim "Приложение осталось здесь: $WORK/$ASSET"' EXIT
else
  trap 'rm -rf "$WORK"' EXIT
fi

bold "Русификатор Desktop Explorer"
dim  "Скачиваю приложение (около 80 МБ)…"
curl -fL --progress-bar -o "$WORK/$ASSET" "$BASE/$ASSET" \
  || die "не удалось скачать $ASSET. Проверьте интернет или скачайте вручную: https://github.com/${REPO}/releases/latest"

# Контрольная сумма: файл мог обрезаться на плохой связи или быть подменён
# по дороге. SHA256SUMS лежит в том же релизе, что и приложение.
if curl -fsSL -o "$WORK/SHA256SUMS" "$BASE/SHA256SUMS" 2>/dev/null; then
  EXPECTED="$(awk -v a="$ASSET" '$2 == a || $2 == "*"a {print $1}' "$WORK/SHA256SUMS" | head -n1)"
  if [ -n "$EXPECTED" ]; then
    ACTUAL="$(shasum -a 256 "$WORK/$ASSET" | awk '{print $1}')"
    [ "$EXPECTED" = "$ACTUAL" ] || die "контрольная сумма не совпала — файл скачался повреждённым. Попробуйте ещё раз."
    dim "Контрольная сумма совпала."
  fi
else
  dim "Не удалось проверить контрольную сумму — продолжаю."
fi

chmod +x "$WORK/$ASSET"
# Файлы, скачанные curl, карантин не получают, но если он всё же есть —
# снимаем: иначе Gatekeeper откажется запускать неподписанное приложение.
xattr -d com.apple.quarantine "$WORK/$ASSET" 2>/dev/null || true
# На Apple Silicon процесс без подписи убивается ядром. Релизы подписаны
# ad-hoc в CI; если подпись всё же не прошла проверку, ставим свою.
codesign -v "$WORK/$ASSET" >/dev/null 2>&1 || codesign --force --sign - "$WORK/$ASSET" >/dev/null 2>&1 || true

# Скрипт пришёл в bash по конвейеру, значит его stdin — это curl, а не
# клавиатура: без /dev/tty мастер получил бы EOF на первом же вопросе.
if [ -r /dev/tty ]; then
  "$WORK/$ASSET" < /dev/tty
else
  "$WORK/$ASSET"
fi
