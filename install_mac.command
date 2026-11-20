#!/bin/bash
# NEON.DOC — полная установка на macOS (Apple Silicon M1–M5).
# Ставит всё сам: Python и библиотеки, Ollama, языковую модель Qwen под объём памяти,
# Whisper для расшифровки (MLX), модели разделения по участникам, LibreOffice для PDF (если нет Word),
# и создаёт приложение NEON.DOC. Повторный запуск = обновление/докачка, данные не трогаются.
cd "$(dirname "$0")" || exit 1
APP_DIR="$(pwd)"
LOG="$APP_DIR/install_mac.log"
exec > >(tee -a "$LOG") 2>&1
echo "──── $(date) ────"

c()    { printf "\n\033[1;35m%s\033[0m\n" "$*"; }
ok()   { printf "\033[1;32m✓ %s\033[0m\n" "$*"; }
warn() { printf "\033[1;33m! %s\033[0m\n" "$*"; }
die()  { printf "\033[1;31m✗ %s\033[0m\n" "$*"; echo "Подробности: $LOG"; read -r -p "Enter — закрыть"; exit 1; }

printf "\033[1;36m"
cat <<'BANNER'
 _   _ _____ ___  _   _   ____   ___   ____
| \ | | ____/ _ \| \ | | |  _ \ / _ \ / ___|
|  \| |  _|| | | |  \| | | | | | | | | |
| |\  | |__| |_| | |\  |_| |_| | |_| | |___
|_| \_|_____\___/|_| \_(_)____/ \___/ \____|   установка для Mac
BANNER
printf "\033[0m"
echo "Папка программы: $APP_DIR"
[ "$(uname -m)" = "arm64" ] || warn "Это не Apple Silicon — расшифровка будет на процессоре и медленной."
case "$APP_DIR" in */Downloads/*|*/Загрузки/*) warn "Программа лежит в «Загрузках». Лучше перенести папку NEON.DOC, например, в «Документы» и запустить установку оттуда.";; esac

MEM=$(( $(sysctl -n hw.memsize) / 1073741824 ))
FREE=$(df -g "$HOME" | awk 'NR==2{print $4}')
if   [ "$MEM" -ge 48 ]; then MODEL="qwen3.6:27b";     MSIZE=18
elif [ "$MEM" -ge 32 ]; then MODEL="qwen3.6:35b-a3b"; MSIZE=23
else                         MODEL="qwen3.5:9b";      MSIZE=7; fi
NEED=$(( MSIZE + 6 ))
echo "Память: ${MEM} ГБ → модель $MODEL.  Свободно на диске: ${FREE} ГБ (нужно ~${NEED} ГБ)."
[ "${FREE:-999}" -ge "$NEED" ] || warn "Места может не хватить — освободи диск, иначе модель не скачается."
echo "Всё вместе займёт 20–60 минут (в основном скачивание). Компьютер не усыпляй."

xattr -dr com.apple.quarantine "$APP_DIR" 2>/dev/null
chmod +x "$APP_DIR"/*.command 2>/dev/null
caffeinate -dimsu -w $$ &   # не засыпать, пока идёт установка

# ─── 1. Python ───────────────────────────────────────────────────────────────
c "1/7  Python 3.12"
export PATH="$HOME/.local/bin:$PATH"
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh || die "Не удалось скачать uv — проверь интернет"
  export PATH="$HOME/.local/bin:$PATH"
fi
[ -x "$APP_DIR/.venv/bin/python" ] || uv venv --python 3.12 "$APP_DIR/.venv" || die "Не удалось создать окружение Python"
PY="$APP_DIR/.venv/bin/python"
ok "$("$PY" --version)"

# ─── 2. Библиотеки ───────────────────────────────────────────────────────────
c "2/7  Библиотеки (окно, документы, PDF, расшифровка, микрофон)"
uv pip install --python "$PY" -r "$APP_DIR/requirements-mac.txt" || die "Ошибка установки библиотек"
ok "библиотеки установлены"

# ─── 3. Ollama ───────────────────────────────────────────────────────────────
c "3/7  Ollama (движок языковых моделей)"
find_ollama() {
  for p in /Applications/Ollama.app/Contents/Resources/ollama "$HOME/Applications/Ollama.app/Contents/Resources/ollama"; do
    [ -x "$p" ] && { echo "$p"; return; }; done
  command -v ollama 2>/dev/null
}
OLLAMA="$(find_ollama)"
if [ -z "$OLLAMA" ]; then
  DEST=/Applications; [ -w /Applications ] || { DEST="$HOME/Applications"; mkdir -p "$DEST"; }
  if curl -L --fail -o /tmp/Ollama-darwin.zip https://ollama.com/download/Ollama-darwin.zip 2>/dev/null; then
    ditto -x -k /tmp/Ollama-darwin.zip "$DEST" && rm -f /tmp/Ollama-darwin.zip
  elif curl -L --fail -o /tmp/Ollama.dmg https://ollama.com/download/Ollama.dmg; then
    MNT=$(mktemp -d); hdiutil attach /tmp/Ollama.dmg -nobrowse -quiet -mountpoint "$MNT" \
      && ditto "$MNT/Ollama.app" "$DEST/Ollama.app"; hdiutil detach "$MNT" -quiet; rm -f /tmp/Ollama.dmg
  fi
  xattr -dr com.apple.quarantine "$DEST/Ollama.app" 2>/dev/null
  OLLAMA="$(find_ollama)"
  if [ -z "$OLLAMA" ]; then
    warn "Автоматически не вышло. Открываю страницу загрузки: установи Ollama, запусти и нажми Enter здесь."
    open "https://ollama.com/download/mac"; read -r
    OLLAMA="$(find_ollama)"; [ -n "$OLLAMA" ] || die "Ollama не найден"
  fi
fi
open -ga Ollama 2>/dev/null || open -g "$(dirname "$(dirname "$(dirname "$OLLAMA")")")" 2>/dev/null
for i in $(seq 1 60); do curl -s http://127.0.0.1:11434/api/version >/dev/null && break; sleep 1; done
curl -s http://127.0.0.1:11434/api/version >/dev/null && ok "Ollama работает" || die "Ollama не запустился — открой приложение Ollama и запусти установку снова"

# ─── 4. Языковая модель ──────────────────────────────────────────────────────
c "4/7  Языковая модель $MODEL (~${MSIZE} ГБ)"
for try in 1 2 3; do "$OLLAMA" pull "$MODEL" && break; warn "обрыв — пробую ещё ($try/3)"; sleep 5; done
"$OLLAMA" list | grep -q "^${MODEL}" && ok "модель $MODEL готова" || warn "Модель не скачалась — запусти установку ещё раз, докачается"

"$PY" - "$MODEL" <<'PYCODE'
import sys, yaml, pathlib
p = pathlib.Path("settings.yaml")
s = (yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else None) or {}
s["model"] = sys.argv[1]
s["ollama_url"] = "http://127.0.0.1:11434"
if s.get("whisper_device") in ("cuda", None):
    s["whisper_device"] = "auto"
s.setdefault("whisper_model", "large-v3-turbo")
p.write_text(yaml.safe_dump(s, allow_unicode=True, sort_keys=False), encoding="utf-8")
print("settings.yaml: model =", s["model"])
PYCODE

# ─── 5. Whisper и диаризация ─────────────────────────────────────────────────
c "5/7  Расшифровка: Whisper (MLX) и разделение по участникам"
"$PY" "$APP_DIR/tools/mac_setup.py" models

# ─── 6. PDF ──────────────────────────────────────────────────────────────────
c "6/7  PDF"
"$PY" "$APP_DIR/tools/mac_setup.py" office

# ─── 7. Приложение ───────────────────────────────────────────────────────────
c "7/7  Приложение NEON.DOC"
APP="$HOME/Applications/NEON.DOC.app"
mkdir -p "$HOME/Applications"; rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cat > "$APP/Contents/MacOS/NEON.DOC" <<SH
#!/bin/bash
cd "$APP_DIR"
open -ga Ollama 2>/dev/null
for i in \$(seq 1 20); do curl -s http://127.0.0.1:11434/api/version >/dev/null && break; sleep 0.5; done
exec "$APP_DIR/.venv/bin/python" -m neondoc > "$APP_DIR/neondoc.log" 2>&1
SH
chmod +x "$APP/Contents/MacOS/NEON.DOC"
cat > "$APP/Contents/Info.plist" <<'PL'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>NEON.DOC</string>
  <key>CFBundleDisplayName</key><string>NEON.DOC</string>
  <key>CFBundleIdentifier</key><string>local.neondoc.app</string>
  <key>CFBundleExecutable</key><string>NEON.DOC</string>
  <key>CFBundleIconFile</key><string>icon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>2.2</string>
  <key>CFBundleVersion</key><string>2.2</string>
  <key>LSMinimumSystemVersion</key><string>13.5</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSMicrophoneUsageDescription</key><string>NEON.DOC записывает голос для диктовки и встреч.</string>
  <key>NSAppleEventsUsageDescription</key><string>NEON.DOC просит Word сохранить документ в PDF.</string>
</dict></plist>
PL
ICONSET="$(mktemp -d)/icon.iconset"; mkdir -p "$ICONSET"
SRC="$APP_DIR/neondoc/static/icon.png"
for s in 16 32 128 256 512; do
  sips -z $s $s "$SRC" --out "$ICONSET/icon_${s}x${s}.png" >/dev/null 2>&1
  sips -z $((s*2)) $((s*2)) "$SRC" --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null 2>&1
done
iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/icon.icns" 2>/dev/null || cp "$SRC" "$APP/Contents/Resources/icon.png"
touch "$APP"
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$APP" 2>/dev/null
# ярлык в Dock (если ещё нет)
if ! defaults read com.apple.dock persistent-apps 2>/dev/null | grep -q "NEON.DOC.app"; then
  defaults write com.apple.dock persistent-apps -array-add "<dict><key>tile-data</key><dict><key>file-data</key><dict><key>_CFURLString</key><string>file://$APP/</string><key>_CFURLStringType</key><integer>15</integer></dict></dict></dict>" && killall Dock 2>/dev/null
fi
ok "NEON.DOC.app — в Launchpad, Spotlight и в Dock"

"$PY" "$APP_DIR/tools/mac_setup.py" check && ok "Всё готово." || warn "Есть замечания выше — можно запустить установку ещё раз, она докачает недостающее."

c "Запускаю NEON.DOC…"
open "$APP"
read -r -p "Enter — закрыть это окно"
