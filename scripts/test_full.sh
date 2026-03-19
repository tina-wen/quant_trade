#!/bin/bash

set -euo pipefail

# 全量测试：包含integration
uv run python -m pytest tests/ -q
