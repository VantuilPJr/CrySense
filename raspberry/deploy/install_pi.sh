#!/usr/bin/env bash
set -euo pipefail

# Execute no Raspberry a partir da raiz do projeto: sudo ./deploy/install_pi.sh
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_DIR="/opt/crysense"
SERVICE_USER="crysense"

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  echo "Usuário $SERVICE_USER não existe. Crie-o no Raspberry Pi Imager ou ajuste SERVICE_USER."
  exit 1
fi

apt-get update
apt-get install -y python3-venv python3-dev build-essential rsync \
  libportaudio2 portaudio19-dev libsndfile1 libopenblas-dev libjpeg-dev \
  i2c-tools spi-tools v4l-utils device-tree-compiler fonts-dejavu-core

install -d -o "$SERVICE_USER" -g "$SERVICE_USER" "$TARGET_DIR"
rsync -a --delete --exclude '.venv' --exclude 'data' --exclude 'datasetIA1' --exclude 'datasetIA2' \
  "$SOURCE_DIR/" "$TARGET_DIR/"
chown -R "$SERVICE_USER:$SERVICE_USER" "$TARGET_DIR"

# INMP441 + MAX98357A compartilham a única controladora I2S do Pi 3B.
# O overlay cria uma única placa ALSA full-duplex (entrada no GPIO20 e saída
# no GPIO21), usando GPIO22 apenas como sinal interno com pull-up.
OVERLAY_SOURCE="$TARGET_DIR/deploy/crysense-i2s-full-duplex-overlay.dts"
OVERLAY_TARGET="/boot/firmware/overlays/crysense-i2s-full-duplex.dtbo"
BOOT_CONFIG="/boot/firmware/config.txt"
BOOT_CHANGED=false
dtc -@ -I dts -O dtb -o "$OVERLAY_TARGET" "$OVERLAY_SOURCE"

if ! grep -qx 'dtoverlay=crysense-i2s-full-duplex' "$BOOT_CONFIG"; then
  cp -an "$BOOT_CONFIG" "$BOOT_CONFIG.crysense-before-full-duplex"
  if grep -qx 'dtoverlay=i2s-dac' "$BOOT_CONFIG"; then
    sed -i 's/^dtoverlay=i2s-dac$/dtoverlay=crysense-i2s-full-duplex/' "$BOOT_CONFIG"
  else
    sed -i '$a dtoverlay=crysense-i2s-full-duplex' "$BOOT_CONFIG"
  fi
  BOOT_CHANGED=true
fi

sudo -u "$SERVICE_USER" python3 -m venv "$TARGET_DIR/.venv"
sudo -u "$SERVICE_USER" "$TARGET_DIR/.venv/bin/python" -m pip install --upgrade pip
sudo -u "$SERVICE_USER" "$TARGET_DIR/.venv/bin/pip" install "$TARGET_DIR[pi,camera]"

if [ ! -f /etc/crysense.env ]; then
  install -m 600 -o root -g root "$TARGET_DIR/.env.example" /etc/crysense.env
  sed -i 's|CRYSENSE_HOME=.*|CRYSENSE_HOME=/opt/crysense|' /etc/crysense.env
  sed -i 's/CRYSENSE_ENABLE_CAMERA=false/CRYSENSE_ENABLE_CAMERA=true/' /etc/crysense.env
  sed -i 's/CRYSENSE_ENABLE_SENSOR=false/CRYSENSE_ENABLE_SENSOR=true/' /etc/crysense.env
  sed -i 's/CRYSENSE_ENABLE_TFT=false/CRYSENSE_ENABLE_TFT=true/' /etc/crysense.env
fi

set_env() {
  local name="$1"
  local value="$2"
  if grep -q "^${name}=" /etc/crysense.env; then
    sed -i "s|^${name}=.*|${name}=${value}|" /etc/crysense.env
  else
    sed -i "\$a${name}=${value}" /etc/crysense.env
  fi
}

set_env CRYSENSE_ENABLE_AUDIO true
set_env CRYSENSE_AUDIO_INPUT_DEVICE snd_rpi_hifiberry_dac8x
set_env CRYSENSE_AUDIO_OUTPUT_DEVICE snd_rpi_hifiberry_dac8x
set_env CRYSENSE_AUDIO_INPUT_CHANNELS 2
set_env CRYSENSE_AUDIO_INPUT_CHANNEL 0
set_env CRYSENSE_AUDIO_OUTPUT_CHANNELS 2

install -m 644 "$TARGET_DIR/deploy/crysense.service" /etc/systemd/system/crysense.service
systemctl daemon-reload
systemctl enable crysense.service

if [ "$BOOT_CHANGED" = true ]; then
  echo "Instalado. Reinicie o Raspberry agora para carregar o I2S full-duplex: sudo reboot"
else
  systemctl restart crysense.service
  echo "Instalado e serviço reiniciado."
fi
