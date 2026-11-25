# Desktop tool access

Lumen connects its assistant to local tools through the Model Context Protocol (MCP). The installed desktop integration uses the name `cachyos` and the command `lumen-mcp`. It communicates through a local process.

## See what is available

Open **Settings → Capabilities & extensions** and choose **Load capabilities**. The MCP tab shows configured tool connections and their status. The plugins tab lists configured OpenCode plugins, and the skills tab lets you inspect the instructions available to the assistant. This view reads the configuration for the selected working directory. Each conversation still has its own permissions.

The current tool list depends on the installation and its permissions. Common read operations include inspecting processes, disks, sensors, package or service status, searching selected file locations and checking a task's progress. File results can carry excerpts. A filename match alone does not establish what the file says.

For a system issue, first ask Lumen to inspect the relevant service or log. If you want it to change something, specify the desired result and review the tool request. A saved task proposal requires its own approval. After an interrupted write, check the target before trying it again.

## Set up the integration

A normal user installation sets up the desktop integration. To configure it later, run `lumen-setup`. To omit it during a manual user install, use `./install.sh --no-mcp`. Existing disabled integrations and their settings are preserved. Reconnect the engine after a configuration change.

For a manually configured MCP client, use your installed executable's absolute path:

```json
{
  "mcp": {
    "cachyos": {
      "type": "local",
      "command": ["/absolute/path/to/lumen/bin/lumen-mcp"],
      "enabled": true
    }
  }
}
```

Optional write actions are disabled by default. Setting `LUMEN_MCP_ACTIONS=1` enables the eligible tools. Engine permissions and any required native confirmation still apply. Keep credentials out of prompts and command arguments.

[Using Lumen Desktop](LUMEN-GUIDE.md) · [Guide index](docs/README.md)
