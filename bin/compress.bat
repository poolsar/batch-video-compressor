@echo off
py "C:\sandbox\batch-video-compressor\compress.py" %*
exit /b %ERRORLEVEL%