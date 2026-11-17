@echo off
rem Builds the sample extension DLL. Run from anywhere; needs the C++ workload.
set VSDEV="C:\Program Files\Microsoft Visual Studio\18\Community\Common7\Tools\VsDevCmd.bat"
if not exist %VSDEV% (
  echo Could not find Visual Studio at %VSDEV%
  exit /b 1
)
call %VSDEV% -arch=x64 >nul
if errorlevel 1 exit /b %errorlevel%
cd /d "%~dp0"
cl /nologo /LD /O2 mathx.cpp /Fe:mathx.dll
exit /b %errorlevel%
