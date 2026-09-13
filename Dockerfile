# ============================================================
#  AI 种田经营游戏 · 运行镜像
#  构建： docker build -t ai-farm-tycoon .
#  运行： docker run --rm -p 8686:8686 ai-farm-tycoon
#  说明： 游戏代码位于 ./game，本文件把整个应用复制到 /app 并监听 0.0.0.0:8686
# ============================================================
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8686 \
    HOST=0.0.0.0

WORKDIR /app

# 先装依赖，利用构建缓存
COPY game/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# 再复制应用代码
COPY game/ /app/

# 非 root 运行，降低容器权限
RUN useradd --create-home --shell /usr/sbin/nologin farmer \
    && chown -R farmer:farmer /app
USER farmer

EXPOSE 8686

HEALTHCHECK --interval=15s --timeout=4s --start-period=5s --retries=4 \
    CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:%s/api/health'%os.environ.get('PORT','8686'),timeout=3)"

CMD ["python", "app.py"]
