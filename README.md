# Jupyter AI Claude Code

Jupyter AI integration with Claude Code persona for enhanced development capabilities.

## Features

- **Claude Code Integration**: Full Claude Code persona for Jupyter AI
- **Continuous Conversation**: Maintains conversation context across multiple messages
- **Development Tools**: Access to Claude Code's built-in development tools
- **Seamless Integration**: Works with existing Jupyter AI workflow
- **Template Management**: Interactive task progress tracking and updates

## User installation

### Requirements

- JupyterLab >= 4.0.0

### Install

To install the extension, execute:

```bash
pip install jupyter-ai-claude-code
```

### Uninstall

To remove the extension, execute:

```bash
pip uninstall jupyter-ai-claude-code
```

## Developer Setup

This project uses [pixi.sh](https://pixi.sh) for dependency management and environment setup.

### Prerequisites

Install pixi.sh:

```bash
curl -fsSL https://pixi.sh/install.sh | bash
```

### Installation

1. Clone the repository:

```bash
git clone <repository-url>
cd jupyter-ai-claude-code
```

2. Enter the pixi shell environment:

```bash
pixi shell
```

## Usage

### Start JupyterLab

```bash
pixi run start
```

This will start JupyterLab with the Jupyter AI extension and Claude Code persona available.

### Using Claude Code Persona

1. Open JupyterLab
2. Open the Jupyter AI chat panel
3. Select "Claude" persona
4. Interact with Claude Code's development tools

#### Continuous Conversation

The Claude Code persona now supports continuous conversation, which maintains context across multiple messages in a chat session. This allows Claude to:

- Remember previous questions and answers
- Build upon earlier context in the conversation
- Provide more coherent multi-turn interactions

**Session Management:**

The persona automatically manages conversation sessions. Each time you send a message,
it's added to the ongoing conversation context.

**How it works:**

- The first message automatically creates a new `ClaudeSDKClient` session.
- Subsequent messages reuse the same client to maintain conversation context.
- The client persists until you start a new session in the chat window.

### Build the Package

The package is automatically installed in editable mode during `pixi shell`. To manually build:

```bash
pixi run python -m build
```

## Development

The package source code is located in `src/jupyter_ai_claude_code/`.

## Dependencies

- **JupyterLab**: Latest stable version from conda-forge
- **Jupyter AI**: Version 3.0.0b5 from PyPI
- **Claude Code SDK**: For Claude Code integration
- **Python**: >=3.8

## License

Revised BSD
