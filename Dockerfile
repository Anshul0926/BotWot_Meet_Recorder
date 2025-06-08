# Use the Python 3.12 slim image
FROM python:3.12-slim

# Install system dependencies (including distutils, pulseaudio, and other necessary tools)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gnupg \
    ca-certificates \
    apt-transport-https \
    wget \
    ffmpeg \
    xvfb \
    pulseaudio \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    python3-setuptools \
    python3-pip \
    python3-distutils \
    && rm -rf /var/lib/apt/lists/*

# Fetch & dearmor Google’s signing key, add Chrome repo
RUN wget -qO - https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor --yes -o /usr/share/keyrings/google-chrome-archive-keyring.gpg && \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome-archive-keyring.gpg] \
    http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list

# Install Google Chrome
RUN apt-get update && \
    apt-get install -y --no-install-recommends google-chrome-stable && \
    rm -rf /var/lib/apt/lists/*

# Expose the required port for Flask
EXPOSE 5001

# Set working directory
WORKDIR /app

# Copy the application code into the container
COPY . .

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Create a non-root user for security reasons
RUN useradd -m botuser && \
    echo "botuser:botpassword" | chpasswd && \
    usermod -aG audio botuser

# Set environment variable for pulseaudio
ENV PULSE_SERVER=unix:/run/user/1000/pulse/native

# Remove any existing Xvfb lock file to avoid display conflicts
RUN rm -f /tmp/.X99-lock

# Switch to the new user to avoid running as root
USER botuser

# Start pulseaudio and Xvfb, then run the application
ENTRYPOINT ["/bin/sh", "-c", "pulseaudio --start --exit-idle-time=-1 && Xvfb :99 -screen 0 1920x1080x24 & export DISPLAY=:99 && exec python3 google_meet_bot_web.py"]
