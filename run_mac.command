#!/bin/bash
# NEON.DOC — запуск на macOS (если не пользуешься NEON.DOC.app)
cd "$(dirname "$0")" || exit 1
[ -x .venv/bin/python ] || { echo "Сначала запусти install_mac.command"; read -r; exit 1; }
open -ga Ollama 2>/dev/null
.venv/bin/python -m neondoc > neondoc.log 2>&1 || { echo "Ошибка — см. neondoc.log"; tail -20 neondoc.log; read -r; }
