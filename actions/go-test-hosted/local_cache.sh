#!/usr/bin/env bash
# 自建 runner 的 Go 缓存快照：job 开始解压到 runner 内存盘，结束时按条件写回节点本地目录。
# CI_CACHE_DIR 由 runner Pod 提供；托管 runner 不调用本脚本。
set -euo pipefail
mode="$1"
if [ -z "${CI_CACHE_DIR:-}" ] || [ ! -d "$CI_CACHE_DIR/go" ]; then
  echo "未提供本地缓存目录，跳过。"
  exit 0
fi
dir="$CI_CACHE_DIR/go/${GITHUB_REPOSITORY//\//_}"
file="$dir/$(go env GOVERSION)${CACHE_SUFFIX:-}.tar.zst"
gocache="$(go env GOCACHE)"
moddownload="$(go env GOMODCACHE)/cache/download"
start=$(date +%s)
case "$mode" in
  restore) 
    if [ ! -f "$file" ]; then
      echo "没有缓存快照：$file"
      exit 0
    fi
    mkdir -p "$gocache" "$moddownload"
    tar -C / --use-compress-program=unzstd -xf "$file"
    echo "已恢复 $(du -sh "$file" | cut -f1) 快照，用时 $(( $(date +%s) - start ))s"
    ;;
  save)
    # 默认分支推送总是刷新；其他事件只在快照不存在时写入一次，避免 PR 反复覆盖。
    if [ -f "$file" ] && { [ "$GITHUB_EVENT_NAME" != push ] || [ "$GITHUB_REF" != "refs/heads/$DEFAULT_BRANCH" ]; }; then
      echo "非默认分支推送且快照已存在，不写回。"
      exit 0
    fi
    mkdir -p "$dir" "$gocache" "$moddownload"
    tmp="$file.tmp.$$"
    tar -C / --use-compress-program='zstd -T0 -3' -cf "$tmp" "${gocache#/}" "${moddownload#/}"
    mv -f "$tmp" "$file"
    echo "已写回 $(du -sh "$file" | cut -f1) 快照，用时 $(( $(date +%s) - start ))s"
    ;;
  *)
    echo "::error::未知模式 $mode"
    exit 1
    ;;
esac
