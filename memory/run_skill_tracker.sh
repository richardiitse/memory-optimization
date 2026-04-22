#!/bin/bash
# Skill Tracker 自动扫描 - 每12小时运行
cd "$(dirname "$0")"
python3 skill_tracker.py scan --save >> ../logs/skill_tracker.log 2>&1