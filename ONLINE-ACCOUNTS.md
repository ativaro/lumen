# Use online storage in Files

Use **Online accounts** in Settings to connect Google Drive, OneDrive, Dropbox or an HTTPS WebDAV folder. Each account has its own name and local configuration. You can add more than one account from the same provider.

1. Open **Online accounts**, add an account, select its provider and choose a recognizable name.
2. For Google Drive, OneDrive or Dropbox, follow the sign-in flow in the browser. Review which account and permissions you are granting. For WebDAV, enter the HTTPS folder URL and credentials. Lumen checks that the folder can be listed before saving it.
3. Open the account in **Lumen Files** and browse to a folder you recognize. To check write access, copy a disposable file there and verify the result in the provider's own interface.

Google sign-in requires a configured desktop OAuth client. If the packaged sign-in is unavailable, use the advanced option with your own client. OneDrive can prompt you to choose the intended drive. Online storage uses rclone. A provider login and an assistant's permission to use a file are separate decisions. [Google Drive sign-in and client setup](packaging/GOOGLE_DRIVE.md)

## Disconnect an account

Finish active transfers first. A mounted connection may require signing out of the desktop session before it can be removed. Remove the connection in Settings. To withdraw the provider's grant as well, revoke it in the provider's account settings.

Account configuration and tokens live in private files in your user profile. WebDAV password obfuscation in rclone is reversible. Protect the profile and any backups that contain it.

## Network shares

For an ordinary network share, use the network connection control in Files (**Ctrl+K**). Enter the address for the supported SMB, SFTP or WebDAV location and use the desktop login prompt if required. Check that the share is reachable before moving files. [Files and offline copies](files/README.md#network-folders-and-versions)

[Guide index](docs/README.md)
