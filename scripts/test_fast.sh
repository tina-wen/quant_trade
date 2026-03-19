#!/bin/bash

set -euo pipefail

# 快速本地回归：跳过integration/slow，仅跑快速测试
uv run python -m pytest tests/ -q -m "not integration and not slow"
