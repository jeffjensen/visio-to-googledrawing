@echo off
rem vsdx2drawing.bat <file.vsdx | file.emf | folder> ... [options] - convert a Visio file and upload each page to Google Drive as a Drawing (see README.adoc)
"%~dp0.venv\Scripts\python.exe" -I "%~dp0vsdx2drawing.py" %*
