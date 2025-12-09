import os
import json
import requests
import smtplib
from email.mime.text import MIMEText

# ==========================
# Configuration
# ==========================
API_URL = "https://deals-dev.innocode.no/api/v1/newspapers/71/customers?filter%5Bsources%5D=fetching_error&page=1&per=10"

HEADERS = {
    "Authorization": os.environ.get("API_TOKEN"),  # just the token
    "Admin-Token": os.environ.get("ADMIN_TOKEN"),
    "Newspaper-Token": os.environ.get("NEWSPAPER_TOKEN"),
    "Accept": "application/json"
}

EMAIL_FROM = "ivan.vatamaniuk@innocode.no"  # sender
EMAIL_TO = "ivan.vatamaniuk@innocode.no"    # recipient
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASS = os.environ.get("SMTP_PASS")

SNAPSHOT_FILE = "previous_errors.json"  # stores errors already seen


# ==========================
# Functions
# ==========================
def send_email(subject, body):
    """Send email via SMTP TLS."""
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as smtp:
        smtp.starttls()
        smtp.login(SMTP_USER, SMTP_PASS)
        smtp.send_message(msg)


def fetch_advertisers():
    """Fetch current advertisers with errors from API."""
    resp = requests.get(API_URL, headers=HEADERS)
    resp.raise_for_status()
    data = resp.json().get("data", [])

    advertisers = {}
    for adv in data:
        adv_id = adv.get("id")
        adv_name = adv.get("name", "Unknown Advertiser")

        flagged_sources = {
            str(src["id"]): {
                "name": src.get("name", "Unknown source"),
                "source_type": src.get("source_type", "Unknown type"),
                "sync_failed_at": src.get("sync_failed_at")
            }
            for src in adv.get("sources", [])
            if src.get("fetching_enabled") and src.get("sync_failed_at") is not None
        }

        if flagged_sources:
            advertisers[adv_id] = {
                "name": adv_name,
                "sources": flagged_sources
            }
    return advertisers


def format_email_body(adv_name, sources):
    """Prepare email body text for one advertiser."""
    lines = [f"Advertiser: {adv_name}", ""]
    for src_id, src_info in sources.items():
        lines.append(f"- Source: {src_info['name']} ({src_info['source_type']})")
        lines.append(f"  Disconnected at: {src_info['sync_failed_at']}")
        lines.append("")
    return "\n".join(lines)


def load_snapshot():
    """Load previously saved snapshot of errors."""
    try:
        with open(SNAPSHOT_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}  # first run, no snapshot yet


def save_snapshot(snapshot):
    """Save snapshot to JSON file."""
    with open(SNAPSHOT_FILE, "w") as f:
        json.dump(snapshot, f, indent=2)


# ==========================
# Main
# ==========================
def main():
    current_data = fetch_advertisers()
    previous_data = load_snapshot()

    # Determine if this is the first run
    first_run = len(previous_data) == 0
    if first_run:
        print("First run detected: saving current errors as snapshot. No emails will be sent.")
        save_snapshot(current_data)
        return

    # Compare with previous snapshot
    for adv_id, adv_info in current_data.items():
        prev_sources = previous_data.get(str(adv_id), {}).get("sources", {})
        new_sources = {}

        for src_id, src_info in adv_info["sources"].items():
            if src_id not in prev_sources:
                # new error detected
                new_sources[src_id] = src_info
            elif src_info["sync_failed_at"] != prev_sources[src_id].get("sync_failed_at"):
                # error re-occurred after being restored
                new_sources[src_id] = src_info

        if new_sources:
            subject = f"Source error for {adv_info['name']}"
            body = format_email_body(adv_info["name"], new_sources)
            send_email(subject, body)
            print(f"Sent email for advertiser {adv_info['name']}")

    # Update snapshot for next run
    save_snapshot(current_data)


if __name__ == "__main__":
    main()
