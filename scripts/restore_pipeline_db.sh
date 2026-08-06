#!/usr/bin/env bash
# Back-compat wrapper — use restore_pipeline_state.sh
exec bash "$(dirname "$0")/restore_pipeline_state.sh"
