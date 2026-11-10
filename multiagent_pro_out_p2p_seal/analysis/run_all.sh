#!/usr/bin/env bash
# Regenerate everything in results/ and REPORT.md for the run this folder sits in.
# Needs python3 (standard library only) and Graphviz `dot`.
set -euo pipefail
cd "$(dirname "$0")"
python3 fig1_agent_actions.py > /dev/null
python3 fig2_message_analysis.py > /dev/null
python3 make_flowcharts.py
python3 build_report.py
