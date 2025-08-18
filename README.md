# Jupyter AI Claude Code

Jupyter AI integration with Claude Code persona for enhanced development capabilities.

## Features

- **Claude Code Integration**: Full Claude Code persona for Jupyter AI
- **Development Tools**: Access to Claude Code's built-in development tools
- **Seamless Integration**: Works with existing Jupyter AI workflow
- **Template Management**: Interactive task progress tracking and updates

## Setup

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

2. Install dependencies and set up the environment:
```bash
pixi install
```

This will:
- Install JupyterLab from conda-forge
- Install Jupyter AI 3.0.0b5 from PyPI
- Install the package in editable mode

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

### Build the Package

The package is automatically installed in editable mode during `pixi install`. To manually build:

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
