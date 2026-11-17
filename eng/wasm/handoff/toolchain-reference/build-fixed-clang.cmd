@echo off
setlocal EnableExtensions
call "C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvarsall.bat" x64
if errorlevel 1 exit /b %ERRORLEVEL%
set "TASK_NINJA=C:\Program Files\Microsoft Visual Studio\18\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja\ninja.exe"
set "TASK_CMAKE=C:\Program Files\CMake\bin\cmake.exe"
"%TASK_CMAKE%" -S "%~dp0llvm-project\llvm" -B "%~dp0llvm-build" -G Ninja "-DCMAKE_MAKE_PROGRAM=%TASK_NINJA%" -DCMAKE_BUILD_TYPE=Release -DLLVM_ENABLE_PROJECTS=clang -DLLVM_TARGETS_TO_BUILD=WebAssembly -DLLVM_INCLUDE_TESTS=OFF -DCLANG_INCLUDE_TESTS=OFF -DLLVM_INCLUDE_BENCHMARKS=OFF -DLLVM_INCLUDE_EXAMPLES=OFF -DLLVM_ENABLE_ASSERTIONS=ON -DLLVM_PARALLEL_LINK_JOBS=1
if errorlevel 1 exit /b %ERRORLEVEL%
"%TASK_CMAKE%" --build "%~dp0llvm-build" --target clang llvm-mc --parallel 8
exit /b %ERRORLEVEL%
