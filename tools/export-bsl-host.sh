#!/usr/bin/env bash
# Скрипт выгрузки BSL-исходников через 1cv8c на хосте.
# Запускается локально (не в контейнере) — имеет доступ к DISPLAY и всем библиотекам.
# Результат кладёт в $BSL_WORKSPACE (монтируемый в контейнер как /projects).
#
# Использование:
#   ./export-bsl-host.sh "Srvr=as-hp;Ref=ERP_DEMO;Usr=Администратор;" /home/aleksei/projects/erp_demo_bsl
#   ./export-bsl-host.sh "File=/home/aleksei/bases/test" /home/aleksei/projects/test_bsl

set -euo pipefail

CONNECTION="${1:?Usage: $0 <connection_string> <output_dir>}"
OUTPUT_DIR="${2:?Usage: $0 <connection_string> <output_dir>}"
V8_PATH="${V8_PATH:-/opt/1cv8/x86_64/8.3.27.2074}"
LOG_FILE="${OUTPUT_DIR}/export_bsl.log"

mkdir -p "$OUTPUT_DIR"

echo "[$(date '+%H:%M:%S')] Starting BSL export..."
echo "  Connection: $CONNECTION"
echo "  Output dir: $OUTPUT_DIR"

# Парсим строку подключения
SERVER=""
DBREF=""
USER_ARG=""
PWD_ARG=""

IFS=';' read -ra PARTS <<< "$CONNECTION"
for part in "${PARTS[@]}"; do
    key=$(echo "$part" | cut -d= -f1 | tr '[:upper:]' '[:lower:]')
    val=$(echo "$part" | cut -d= -f2-)
    case "$key" in
        srvr) SERVER="$val" ;;
        ref)  DBREF="$val" ;;
        file) SERVER=""; DBREF="" ;;
        usr)  USER_ARG="$val" ;;
        pwd)  PWD_ARG="$val" ;;
    esac
done

# Собираем аргументы 1cv8c
if [ -n "$SERVER" ] && [ -n "$DBREF" ]; then
    CONNECT_ARG="/S ${SERVER}\\${DBREF}"
else
    # Файловая база — берём путь из File=
    FILE_PATH=$(echo "$CONNECTION" | sed 's/.*[Ff]ile=//;s/;.*//')
    CONNECT_ARG="/F ${FILE_PATH}"
fi

CMD=(
    "$V8_PATH/1cv8c"
    "DESIGNER"
    $CONNECT_ARG
)
[ -n "$USER_ARG" ] && CMD+=("/N" "$USER_ARG")
[ -n "$PWD_ARG"  ] && CMD+=("/P" "$PWD_ARG")
CMD+=(
    "/DumpConfigToFiles" "$OUTPUT_DIR"
    "/DisableStartupDialogs"
    "/Out" "$LOG_FILE"
)

echo "[$(date '+%H:%M:%S')] Running: ${CMD[*]}"

# Запускаем с DISPLAY если есть, иначе пробуем без него
if [ -n "${DISPLAY:-}" ]; then
    exec "${CMD[@]}"
else
    # Попробуем первый доступный X-дисплей
    for d in :0 :1 :2; do
        if [ -S "/tmp/.X11-unix/X${d#:}" ] 2>/dev/null; then
            DISPLAY="$d" exec "${CMD[@]}"
            break
        fi
    done
    exec "${CMD[@]}"
fi
