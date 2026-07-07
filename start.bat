@echo off
echo ============================================
echo   AI 国际象棋分析助手 - 启动脚本
echo ============================================
echo.

REM 检查 .env 文件
if not exist .env (
    echo [!] 未找到 .env 文件，正在从 .env.example 创建...
    copy .env.example .env
    echo [!] 请编辑 .env 文件，填入你的 DEEPSEEK_API_KEY
    echo.
)

REM 检查 Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [X] 未找到 Python，请先安装 Python 3.11+
    pause
    exit /b 1
)

REM 检查 Stockfish
where stockfish >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] 未在 PATH 中找到 Stockfish
    echo [!] 请确保 Stockfish 18 已安装并在 PATH 中
    echo [!] 或者设置 STOCKFISH_PATH 环境变量指向 stockfish 可执行文件
    echo.
)

REM 安装依赖
echo [*] 安装 Python 依赖...
pip install -r requirements.txt -q
echo.

REM 启动后端
echo [*] 启动 FastAPI 后端 (端口 8000)...
start "Chess Backend" cmd /c "python -m uvicorn app.api:app --host 0.0.0.0 --port 8000 --reload"
echo [*] 等待后端启动...
timeout /t 3 /nobreak >nul

REM 启动前端
echo [*] 启动 Streamlit 前端 (端口 8501)...
start "Chess Frontend" cmd /c "streamlit run app/frontend.py --server.port 8501"

echo.
echo ============================================
echo   启动完成！
echo   后端: http://localhost:8000
echo   前端: http://localhost:8501
echo   API 文档: http://localhost:8000/docs
echo ============================================
echo.
echo 按任意键退出...
pause >nul
