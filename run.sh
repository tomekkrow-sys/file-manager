#!/usr/bin/env bash
# Uruchamia File Manager (tworzy venv przy pierwszym uruchomieniu).
set -e
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
fi

exec .venv/bin/python file_manager.py "$@"
