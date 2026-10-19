@echo off
rem vsdx2emf.bat <file.vsdx> [out-dir] [options] - one EMF per page of a Visio file (see README.adoc)
"%~dp0.venv\Scripts\python.exe" -I "%~dp0convert.py" %*
