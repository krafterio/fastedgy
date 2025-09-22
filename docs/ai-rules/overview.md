# AI Rules for FastEdgy

**Enhance your AI coding assistant with FastEdgy-specific rules**

AI Rules help your coding assistant (Cursor, GitHub Copilot, etc.) better understand FastEdgy patterns, conventions, and best practices. These rule files provide context about the framework's architecture, coding patterns, and common use cases.

## What are AI Rules?

AI Rules are configuration files that provide context and guidelines to AI coding assistants. They help the AI:

- Understand FastEdgy's specific patterns and conventions
- Generate more accurate and consistent code
- Follow project-specific best practices
- Provide better suggestions for common tasks

## Available Rule Files

FastEdgy provides rules for different aspects of development:

<div class="grid cards" markdown>

-   **:fontawesome-brands-python: FastEdgy Core Rules**

    ---

    Core framework patterns, dependency injection, API routes, and FastEdgy-specific conventions.

    [Learn more →](fastedgy.md)

-   **:fontawesome-brands-python: Python Rules**

    ---

    Python-specific patterns when working with FastEdgy, including async/await, type hints, and Pydantic models.

    [Learn more →](python.md)

-   **:fontawesome-brands-js: JavaScript Rules**

    ---

    JavaScript/TypeScript patterns for frontend development with FastEdgy APIs.

    [Learn more →](javascript.md)

-   **:fontawesome-brands-vuejs: Vue.js Rules**

    ---

    Vue.js-specific patterns when using vue-fastedgy, including composables, stores, and component patterns.

    [Learn more →](vue.md)

</div>

## Prerequisites

**MCP Server Configuration Required**: These AI Rules are designed to work with the MCP server "fastedgy-docs" that provides access to FastEdgy documentation. You must configure the [MCP integration](mcp.md) first before using these rules effectively.

## How to Use

1. **Configure MCP**: Set up the [MCP server integration](mcp.md) to enable documentation access
2. **Choose your AI tool**: These rules work with Cursor, GitHub Copilot, and other AI coding assistants
3. **Select relevant rules**: Pick the rule files that match your development stack
4. **Copy and configure**: Copy the rules to your project's AI configuration
5. **Customize**: Adapt the rules to your specific project needs

## Supported AI Tools

- **Cursor**: Place rules in `.cursor/rules`
- **GitHub Copilot**: Use in workspace configuration or as documentation
- **Other AI assistants**: Adapt format as needed for your tool

## Benefits

- **Faster development**: AI understands FastEdgy patterns immediately
- **Consistent code**: Generate code that follows FastEdgy conventions
- **Better suggestions**: More relevant completions and refactoring suggestions
- **Reduced context switching**: Less need to explain framework concepts

Ready to enhance your AI coding experience with FastEdgy?

[Get Started with AI Rules](fastedgy.md){ .md-button .md-button--primary }
