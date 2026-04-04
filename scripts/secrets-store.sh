#!/usr/bin/env bash
# Store tublemetry ESPHome credentials in macOS Keychain.
# Run once after setting up credentials. Re-run to update values.
set -euo pipefail

SERVICE="tublemetry-esphome"

store() {
  local account="$1"
  local value="$2"
  # Delete existing entry if present (suppress "not found" errors)
  security delete-generic-password -a "$account" -s "$SERVICE" 2>/dev/null || true
  security add-generic-password -a "$account" -s "$SERVICE" -w "$value"
  echo "  stored: $account"
}

SECRETS_FILE="$(dirname "$0")/../esphome/secrets.yaml"

if [[ ! -f "$SECRETS_FILE" ]]; then
  echo "Error: $SECRETS_FILE not found. Create it from esphome/secrets.yaml.example first."
  exit 1
fi

read_secret() {
  grep "^$1:" "$SECRETS_FILE" | sed 's/^[^:]*: *"//' | sed 's/"$//'
}

echo "Storing credentials from esphome/secrets.yaml into Keychain (service: $SERVICE)..."

store "wifi_ssid"     "$(read_secret wifi_ssid)"
store "wifi_password" "$(read_secret wifi_password)"
store "api_key"       "$(read_secret api_key)"
store "ota_password"  "$(read_secret ota_password)"

echo "Done. You can verify with: security find-generic-password -s $SERVICE -a wifi_ssid -w"
