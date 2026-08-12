#!/usr/bin/env bash
# 转发到 Application Support 中的实际脚本（由 install-pipeline-sources-launchd.sh 安装）
exec "${HOME}/Library/Application Support/newsc/run-pipeline-sources.sh" "$@"
