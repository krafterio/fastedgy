---
hide:
  - navigation
---

# Model Context Protocol (MCP)

FastEdgy is compatible with MCP (Model Context Protocol) through a local MCP server that connects to FastEdgy
documentation. This section explains how to configure and use this MCP server to access FastEdgy documentation from
your AI assistant.

## What is MCP?

The Model Context Protocol (MCP) is a protocol developed by Anthropic that allows AI assistants to access external
resources in a secure and structured way. For FastEdgy, this allows your AI assistant to:

- Search through FastEdgy documentation
- Provide accurate answers with links to sources
- Access the most up-to-date documentation information

## Configuration

### Claude Desktop

To use FastEdgy with Claude Desktop, add the following configuration to your MCP configuration file:

**Configuration file location:**

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

**Configuration:**

```json
{
  "mcpServers": {
    "fastedgy-docs": {
      "command": "npx",
      "args": [
        "-y",
        "@serverless-dna/mkdocs-mcp",
        "https://fastedgy.krafter.io",
        "Search FastEdgy documentation (MkDocs) and return concise, source-linked answers."
      ]
    }
  }
}
```

After adding this configuration:

1. Restart Claude Desktop
2. You should see a 🔧 icon next to the MCP server name in the status bar
3. Claude assistant will now have access to FastEdgy documentation

### Cursor IDE

If you are using Cursor IDE, you can also configure MCP to access FastEdgy documentation directly from your editor.

**Configuration for Cursor:**

1. Open Cursor settings
2. Navigate to the MCP section
3. Add the following configuration:

```json
{
  "mcpServers": {
    "fastedgy-docs": {
      "command": "npx",
      "args": [
        "-y",
        "@serverless-dna/mkdocs-mcp",
        "https://fastedgy.krafter.io",
        "Search FastEdgy documentation (MkDocs) and return concise, source-linked answers."
      ]
    }
  }
}
```

### Other IDEs and Editors

The FastEdgy MCP server can be used with any editor or IDE that supports the MCP protocol. The basic configuration
remains the same, only the configuration file location may vary.

## Usage

Once configured, you can ask questions about FastEdgy to your AI assistant, for example:

- "How to configure authentication in FastEdgy?"
- "Show me an example of using queued tasks"
- "How does the container service system work?"
- "What ORM features are available?"

The assistant will be able to provide detailed answers with direct links to the relevant sections of the documentation.

## MCP Server Used

FastEdgy documentation is accessible through the [mkdocs-mcp](https://github.com/serverless-dna/mkdocs-mcp) server
developed by Serverless DNA. This external MCP server connects to FastEdgy's published documentation and provides:

- Access to the MkDocs Lunr.js search index
- Efficient local search capabilities
- Structured results with links to sources

## Troubleshooting

### MCP server doesn't connect

1. Verify that Node.js is installed on your system
2. Make sure the JSON configuration is valid
3. Restart your IDE/assistant
4. Check application logs for error messages

### No search results

1. Verify that the documentation URL is accessible: [https://fastedgy.krafter.io](https://fastedgy.krafter.io)
2. Make sure your internet connection is working
3. The MCP server downloads the search index at startup

### Performance issues

The MCP server caches the search index locally. If you encounter slowness:

1. Restart the MCP server
2. Check your internet connection
3. The index updates automatically

## Support

If you encounter issues with the MCP integration:

1. Check the [mkdocs-mcp server documentation](https://github.com/serverless-dna/mkdocs-mcp)
2. Open an issue on the [FastEdgy repository](https://github.com/krafterio/fastedgy/issues)
3. Make sure you are using the latest version of the MCP server

---

*This MCP integration significantly improves the development experience by providing instant and contextual access to
FastEdgy documentation from your development environment.*
