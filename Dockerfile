FROM python:3.12-slim

# 1) System deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      wget gnupg ca-certificates \
      ffmpeg xvfb pulseaudio \
      libnss3 libatk1.0-0 libatk-bridge2.0-0 \
      libcups2 libdrm2 libxkbcommon0 libxcomposite1 \
      libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2 && \
    rm -rf /var/lib/apt/lists/*

# 2) Chrome
RUN wget -qO - https://dl-ssl.google.com/linux/linux_signing_key.pub \
      | gpg --dearmor --yes \
        -o /usr/share/keyrings/google-chrome-archive-keyring.gpg && \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome-archive-keyring.gpg] \
      http://dl.google.com/linux/chrome/deb/ stable main" \
      > /etc/apt/sources.list.d/google-chrome.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends google-chrome-stable && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5001

# start pulseaudio & Flask
ENTRYPOINT ["sh","-c","pulseaudio --start --system --exit-idle-time=-1 && exec python3 google_meet_bot_web.py"]
