@echo off
chcp 65001 >nul
title Discord Music Bot (Spotify + YouTube Ad-Free)
color 0b


echo ========================================================
echo       Starting Free Discord Music Bot...
echo ========================================================
echo.

:: Ensure python is available
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in your PATH!
    echo Please install Python from https://www.python.org/
    pause
    exit /b
)

:: Run the bot
python bot.py

if %errorlevel% neq 0 (
    echo.
    echo Bot stopped with an error. Please check the message above.
    pause
)
