# Configure Google Drive sign-in

If **Online accounts → Google Drive** opens the Google sign-in page, choose your account there and review the requested access. After you return to Files, open the account and list a folder. A normal user of a configured build does not need to create an OAuth client.

If the default sign-in option is unavailable, use the advanced option with your own **Desktop app** OAuth client. A testing client may be limited to accounts its owner has added as test users. Removing the account from Lumen removes the local connection. You can also revoke the grant in your Google account. [Online accounts guide](../ONLINE-ACCOUNTS.md)

## For people packaging Lumen

1. Enable the Google Drive API in your Google Cloud project. Configure an OAuth consent screen for the intended audience and add test users if appropriate.
2. Create an OAuth client of type **Desktop app**. Download the client configuration to a local file outside the checkout. Lumen uses rclone and a browser with a loopback redirect. The supported full-drive operations require the Drive scope.
3. Pass the file to the build or user installer. Use a real absolute path in place of the example below.

```sh
env LUMEN_GOOGLE_OAUTH_CLIENT_FILE=/path/to/desktop-client.json bash packaging/arch/build-package.sh
```

For a user installation, use `bash install.sh` with the same environment variable. Packaging extracts the installed client ID and client secret. An explicitly selected invalid or missing file stops the build. A distributed desktop client identity is readable by recipients. Keep personal access tokens and refresh tokens out of this file and out of Git. The local Google rclone configuration is stored separately under `~/.config/lumen/google-drive/`.

Before distributing that sign-in option more broadly, check the consent-screen and verification requirements for your audience and scopes. The package build cannot confirm Google's approval. [Google's native-app OAuth documentation](https://developers.google.com/identity/protocols/oauth2/native-app) · [Drive scopes](https://developers.google.com/workspace/drive/api/guides/api-specific-auth)
