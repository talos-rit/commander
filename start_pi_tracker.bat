@echo off
ssh pi@bluey.local "systemctl --user restart pi-tracker && systemctl --user status pi-tracker"
pause
