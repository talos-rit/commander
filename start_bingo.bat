@echo off
cd /d "%~dp0"

uv run --extra simulation python -m src.simulation.viewer --no-demo --real-robot bluey=bluey.local:61616 --start-real
