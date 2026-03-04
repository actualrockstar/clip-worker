from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/drive"]

flow = InstalledAppFlow.from_client_secrets_file("/secrets/oauth_client.json", SCOPES)

# Use host 0.0.0.0 and a fixed port so Docker -> Mac redirect works
creds = flow.run_local_server(host="0.0.0.0", port=8085, open_browser=False)

with open("/secrets/token.json", "w") as f:
    f.write(creds.to_json())

print("Wrote /secrets/token.json")