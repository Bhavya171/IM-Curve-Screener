from pathlib import Path
import msal

CLIENT_ID = "b6bd48fa-55db-41aa-9af8-e74283e478fb"
TENANT_ID = "0753c1a4-2be6-4a86-8763-32ae847e1186"
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPES = [
    "api://28ab8830-42a2-4400-8ef0-07af1dfc1163/access_as_application"
]

CACHE_FILE = Path(__file__).with_name(".msal_token_cache.json")
ENV_FILE = Path(__file__).with_name(".env")


def store_access_token(access_token: str) -> None:
    """Store the latest access token in the folder-local .env file."""
    token_entry = f"LIGHTSTREAMER_TOKEN={access_token}"
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []

    updated_lines = []
    token_replaced = False

    for line in lines:
        key, separator, _ = line.partition("=")
        if separator and key.strip() == "LIGHTSTREAMER_TOKEN":
            if not token_replaced:
                updated_lines.append(token_entry)
                token_replaced = True
            continue
        updated_lines.append(line)

    if not token_replaced:
        updated_lines.append(token_entry)

    ENV_FILE.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")


def get_auth_token():
    cache = msal.SerializableTokenCache()

    if CACHE_FILE.exists():
        cache.deserialize(CACHE_FILE.read_text(encoding="utf-8"))

    app = msal.PublicClientApplication(
        CLIENT_ID,
        authority=AUTHORITY,
        token_cache=cache,
    )

    result = None
    accounts = app.get_accounts()

    if accounts:
        # Returns a cached access token or uses the cached refresh token.
        result = app.acquire_token_silent(
            scopes=SCOPES,
            account=accounts[0],
        )

    if not result:
        # First login, or refresh token can no longer be used.
        flow = app.initiate_device_flow(scopes=SCOPES)

        if "user_code" not in flow:
            raise RuntimeError(
                f"Failed to create device flow: "
                f"{flow.get('error_description')}"
            )

        print(flow["message"])
        result = app.acquire_token_by_device_flow(flow)

    if cache.has_state_changed:
        CACHE_FILE.write_text(cache.serialize(), encoding="utf-8")

    if "access_token" not in result:
        raise RuntimeError(
            f"Failed to get token: {result.get('error_description')}"
        )

    store_access_token(result["access_token"])
    return result


if __name__ == "__main__":
    get_auth_token()
    print(f"Access token saved to {ENV_FILE}")
