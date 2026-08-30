#!/usr/bin/env bash
set -euo pipefail

# Cria um ponto de acesso local que o NetworkManager usa somente quando não
# consegue associar o Raspberry a uma rede Wi-Fi conhecida.
SSID="${1:-CrySense-Setup}"
PASSWORD="${2:?Informe uma senha WPA2 de ao menos 8 caracteres.}"
CONNECTION_NAME="CrySense fallback AP"
INTERFACE="wlan0"

if [ "${#PASSWORD}" -lt 8 ]; then
  echo "A senha do ponto de acesso precisa ter pelo menos 8 caracteres." >&2
  exit 2
fi

# Redes já conhecidas têm prioridade maior. Assim o AP não interrompe a rede
# normal quando ela estiver disponível.
while IFS=: read -r name type; do
  if [ "$type" = "802-11-wireless" ] && [ "$name" != "$CONNECTION_NAME" ]; then
    nmcli connection modify "$name" connection.autoconnect-priority 100
  fi
done < <(nmcli -t -f NAME,TYPE connection show)

if nmcli -t -f NAME connection show | grep -Fxq "$CONNECTION_NAME"; then
  nmcli connection modify "$CONNECTION_NAME" 802-11-wireless.ssid "$SSID"
else
  nmcli connection add type wifi ifname "$INTERFACE" con-name "$CONNECTION_NAME" ssid "$SSID"
fi

nmcli connection modify "$CONNECTION_NAME" \
  connection.autoconnect yes \
  connection.autoconnect-priority -999 \
  connection.autoconnect-retries 0 \
  802-11-wireless.mode ap \
  802-11-wireless.band bg \
  802-11-wireless.powersave 2 \
  wifi-sec.key-mgmt wpa-psk \
  wifi-sec.psk "$PASSWORD" \
  ipv4.method shared \
  ipv4.addresses 10.42.0.1/24 \
  ipv6.method disabled

echo "Ponto de acesso de emergência configurado: $SSID"
echo "Ele usará http://10.42.0.1:8080 quando nenhuma rede Wi-Fi conhecida estiver disponível."
