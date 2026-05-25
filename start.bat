@echo off
chcp 65001 >nul
setlocal

REM ===== 可覆盖配置：启动前设置同名环境变量即可覆盖默认值 =====
if not defined AINR_PORT     set "AINR_PORT=8000"
if not defined AINR_PROXY    set "AINR_PROXY=http://127.0.0.1:10809"
if not defined AINR_NO_PROXY set "AINR_NO_PROXY=localhost,127.0.0.1,api.minimaxi.com,mp.weixin.qq.com,zhipuai.cn,deepseek.com,qbitai.com,jiqizhixin.com,latepost.com,infoq.cn,36kr.com,xinzhiyuan.com,tmtpost.com,aibase.com"

REM HF 镜像：设置 AINR_HF_ENDPOINT 后由子进程继承（留空＝用 HuggingFace 官方源）
REM   新机器免代理可设为 https://hf-mirror.com
if defined AINR_HF_ENDPOINT set "HF_ENDPOINT=%AINR_HF_ENDPOINT%"

echo ============================================
echo   AI News Radar - 启动中
echo ============================================
echo.
echo [1/2] 检查 Python 依赖...
set "HTTP_PROXY=%AINR_PROXY%"
set "HTTPS_PROXY=%AINR_PROXY%"
set "NO_PROXY=%AINR_NO_PROXY%"
python -c "import importlib.util as u, sys; mods=['fastapi','uvicorn','feedparser','playwright','bs4','requests','sentence_transformers','apscheduler','yaml','anthropic','openai','dotenv','aiohttp','websockets','twscrape']; missing=[m for m in mods if u.find_spec(m) is None]; print('   缺失: '+', '.join(missing)) if missing else None; sys.exit(1 if missing else 0)"
if errorlevel 1 (
    echo   正在安装 backend\requirements.txt 缺失依赖...
    python -m pip install -r backend\requirements.txt
) else (
    echo   依赖完整
)
echo.
echo [2/2] 启动后端服务 (localhost:%AINR_PORT%)...
echo   前端已内置，无需单独启动
echo   代理: %AINR_PROXY%
if defined HF_ENDPOINT (echo   HF 源: %HF_ENDPOINT%) else (echo   HF 源: 官方 huggingface.co)
echo.
start "AI-Radar-Backend" cmd /k "cd /d "%~dp0" && set "PYTHONUNBUFFERED=1" && set "HTTP_PROXY=%AINR_PROXY%" && set "HTTPS_PROXY=%AINR_PROXY%" && set "NO_PROXY=%AINR_NO_PROXY%" && python -u -m uvicorn backend.main:app --port %AINR_PORT% --reload"
echo.
timeout /t 3 /nobreak >nul
echo 正在打开浏览器...
start http://localhost:%AINR_PORT%
echo.
echo ============================================
echo   启动完成！
echo   访问: http://localhost:%AINR_PORT%
echo   API文档: http://localhost:%AINR_PORT%/docs
echo   关闭: 关闭命令行窗口即可
echo ============================================
