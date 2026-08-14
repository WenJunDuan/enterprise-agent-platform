#!/usr/bin/env bash
# 企业智能审核平台 · 每日全量备份
#
# 备份对象（全部为源数据只读，本脚本绝不删除任何源数据）：
#   data/db/platform.sqlite3   业务库（走 SQLite 在线备份，WAL 下 cp 会拿到不一致快照）
#   data/sessions/             会话事件流 / 评标 trace（业务数据，非运行日志）
#   data/submissions/          上传原件（源目录有保留期清理，备份端只增不删）
#   data/ocr-cache/            OCR 缓存（可再生，默认含入；BACKUP_SKIP_OCR_CACHE=1 可跳过）
#   knowledge/                 制度规则与记忆沉淀（**gitignored，仓库无副本，丢失不可恢复**）
#   logs/                      运行日志
#
# 滚动保留：只删除本脚本自己产出的、命名匹配的备份归档，保留最近 BACKUP_KEEP 份（默认 3）。
#
# 用法：
#   bash deploy/backup.sh                          # 备份到默认 /backup
#   BACKUP_ROOT=/mnt/nas/ea-backup bash deploy/backup.sh
#   BACKUP_KEEP=7 bash deploy/backup.sh            # 改保留份数
#   BACKUP_SKIP_OCR_CACHE=1 bash deploy/backup.sh  # 跳过可再生的 OCR 缓存
#
# 定时（每日 02:30）：
#   30 2 * * * cd /opt/enterprise-agent-platform && BACKUP_ROOT=/backup bash deploy/backup.sh >> /var/log/ea-backup.log 2>&1
#
# 恢复见文末「恢复步骤」。备份必须落到**另一块盘或另一台机**，同盘备份挡不住磁盘故障。

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_ROOT="${BACKUP_ROOT:-/backup}"
BACKUP_KEEP="${BACKUP_KEEP:-3}"
BACKUP_SKIP_OCR_CACHE="${BACKUP_SKIP_OCR_CACHE:-0}"
STAMP="$(date +%Y%m%d)"
PREFIX="ea-backup"
DEST_DIR="${BACKUP_ROOT}/${PREFIX}-${STAMP}"

log() { printf '[backup %s] %s\n' "$(date +%H:%M:%S)" "$*"; }
fail() { printf '[backup %s] ERROR: %s\n' "$(date +%H:%M:%S)" "$*" >&2; exit 1; }

command -v sqlite3 >/dev/null 2>&1 || fail "缺少 sqlite3 命令（业务库需在线备份，不能 cp）"
command -v tar >/dev/null 2>&1 || fail "缺少 tar 命令"

mkdir -p "${DEST_DIR}" || fail "无法创建备份目录 ${DEST_DIR}"
cd "${PROJECT_ROOT}"

FAILED=0
MANIFEST="${DEST_DIR}/MANIFEST.txt"
: > "${MANIFEST}"

record() { printf '%s\n' "$*" >> "${MANIFEST}"; }
record "backup_time=$(date -Iseconds)"
record "project_root=${PROJECT_ROOT}"
record "git_commit=$(git -C "${PROJECT_ROOT}" rev-parse --short HEAD 2>/dev/null || echo unknown)"

# --- 1. 业务库：SQLite 在线备份（.backup 是唯一 WAL 安全的方式）---
DB_PATH="data/db/platform.sqlite3"
if [ -f "${DB_PATH}" ]; then
  TMP_DB="${DEST_DIR}/platform.sqlite3"
  if sqlite3 "${DB_PATH}" ".backup '${TMP_DB}'"; then
    # 备份件自身做一次完整性校验，坏档要当场发现而不是恢复时才发现
    if [ "$(sqlite3 "${TMP_DB}" 'PRAGMA integrity_check;')" = "ok" ]; then
      # integrity_check 会打开备份件从而产生 -wal/-shm 附属文件，它们不属于备份内容，清掉
      rm -f "${TMP_DB}-wal" "${TMP_DB}-shm"
      # -f 覆盖同名件：同一天补跑备份是合法操作，不加 -f 会因"已存在"退出且 set -e 会
      # 让脚本死在这里、跳过后续归档与滚动清理（实测踩过）。
      gzip -9 -f "${TMP_DB}"
      record "db=platform.sqlite3.gz size=$(du -h "${TMP_DB}.gz" | cut -f1)"
      log "业务库备份完成 $(du -h "${TMP_DB}.gz" | cut -f1)"
    else
      rm -f "${TMP_DB}"
      FAILED=1
      log "业务库 integrity_check 未通过，已丢弃该备份件"
    fi
  else
    FAILED=1
    log "业务库在线备份失败"
  fi
else
  log "跳过业务库（${DB_PATH} 不存在）"
fi

# --- 2. 目录：tar.gz ---
archive_dir() {
  local src="$1" name="$2"
  if [ ! -d "${src}" ]; then
    log "跳过 ${name}（${src} 不存在）"
    return 0
  fi
  local out="${DEST_DIR}/${name}.tar.gz"
  # tar 退出码：0=正常，1=归档期间有文件被改动（服务在跑时正常，归档仍可用），2=致命错误。
  # 不用 GNU 专有的 --warning=no-file-changed（BSD/macOS tar 不认，实测会让整个归档失败）。
  local rc=0
  tar czf "${out}" "${src}" 2>/dev/null || rc=$?
  if [ "${rc}" -ge 2 ]; then
    rm -f "${out}"
    FAILED=1
    log "${name} 归档失败（tar 退出码 ${rc}）"
    return 0
  fi
  if gzip -t "${out}" 2>/dev/null; then
    if [ "${rc}" -eq 1 ]; then
      log "${name} 归档期间有文件变动（服务运行中属正常），归档校验通过"
    fi
    record "${name}=${name}.tar.gz size=$(du -h "${out}" | cut -f1)"
    log "${name} 备份完成 $(du -h "${out}" | cut -f1)"
  else
    rm -f "${out}"
    FAILED=1
    log "${name} 归档校验失败，已丢弃"
  fi
}

archive_dir "data/sessions" "sessions"
archive_dir "data/submissions" "submissions"
archive_dir "knowledge" "knowledge"
archive_dir "logs" "logs"
if [ "${BACKUP_SKIP_OCR_CACHE}" = "1" ]; then
  log "按 BACKUP_SKIP_OCR_CACHE=1 跳过 OCR 缓存（可再生数据）"
else
  archive_dir "data/ocr-cache" "ocr-cache"
fi

record "status=$([ "${FAILED}" -eq 0 ] && echo ok || echo partial)"

# --- 3. 滚动保留：只删本脚本产出的、命名匹配的目录，永不触碰源数据 ---
# 按目录名（含日期）倒序排，保留最新 BACKUP_KEEP 份。用计数而非 mtime，
# 避免某天没跑导致的误删；用 find -maxdepth 1 精确匹配自身命名，杜绝删到无关目录。
prune() {
  local keep="$1"
  local -a all=()
  while IFS= read -r line; do all+=("${line}"); done < <(
    find "${BACKUP_ROOT}" -maxdepth 1 -type d -name "${PREFIX}-[0-9]*" 2>/dev/null | sort -r
  )
  local total=${#all[@]}
  if [ "${total}" -le "${keep}" ]; then
    log "保留 ${total} 份备份（上限 ${keep}），无需清理"
    return 0
  fi
  local i
  for ((i = keep; i < total; i++)); do
    # 双保险：确认待删路径确实在 BACKUP_ROOT 下且匹配自身命名
    case "${all[i]}" in
      "${BACKUP_ROOT}/${PREFIX}-"*)
        rm -rf "${all[i]}"
        log "已删除过期备份 ${all[i]}"
        ;;
      *)
        log "跳过异常路径 ${all[i]}（不匹配备份命名，未删除）"
        ;;
    esac
  done
}

prune "${BACKUP_KEEP}"

TOTAL_SIZE="$(du -sh "${DEST_DIR}" | cut -f1)"
if [ "${FAILED}" -eq 0 ]; then
  log "备份完成 ${DEST_DIR}（${TOTAL_SIZE}）"
else
  log "备份部分失败 ${DEST_DIR}（${TOTAL_SIZE}）——见上方 ERROR 行，请排查后重跑"
  exit 1
fi

# --- 恢复步骤（人工执行，脚本不自动恢复以免误覆盖生产数据）---
#
#   1. 停服务：systemctl stop enterprise-agent   （或 docker compose down）
#   2. 业务库：
#        gunzip -c /backup/ea-backup-YYYYMMDD/platform.sqlite3.gz > data/db/platform.sqlite3
#        rm -f data/db/platform.sqlite3-wal data/db/platform.sqlite3-shm   # 陈旧 WAL 必须清掉
#        sqlite3 data/db/platform.sqlite3 'PRAGMA integrity_check;'        # 应输出 ok
#   3. 目录（在项目根执行，归档内含相对路径）：
#        tar xzf /backup/ea-backup-YYYYMMDD/knowledge.tar.gz -C .
#        tar xzf /backup/ea-backup-YYYYMMDD/sessions.tar.gz -C .
#        tar xzf /backup/ea-backup-YYYYMMDD/submissions.tar.gz -C .
#   4. 起服务，跑一单评标冒烟确认。
#
# 定期做恢复演练——没验证过的备份等于没有备份。
