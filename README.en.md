# Local AI

**This repository is a fork of the [original Local AI project](https://github.com/OlegChe77/local-ai).** This repository maintains its own development and documentation for the fork.

[Русский](README.md) · **English**

[![Windows 10 and 11](https://img.shields.io/badge/Windows-10%20%7C%2011-0078d6)](#install)
[![Ollama](https://img.shields.io/badge/engine-Ollama-black)](https://ollama.com)
[![MIT license](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)

Your own AI chat on your own PC. The app detects your graphics card, memory and free disk space, **picks a suitable model**, helps install [Ollama](https://ollama.com) and download the model. After setup, chat runs locally: no subscription or account is required.

![Local AI: a chat with a local model, chat list and model stats on the left](docs/screenshots/en/02-chat.png)

Prebuilt packages for this fork are published in this repository's [Releases section](https://github.com/FMulder007/FM-local-ai/releases) when a release archive is available. If no prebuilt release is available yet, you can run the app from source or build it yourself using the instructions below.

Python is not required to run a prebuilt package. The app is designed for Windows 10 and 11.

## Features

- **Picks a model for your hardware.** Detects the graphics card (NVIDIA, AMD), VRAM, RAM and free disk space. Recommends the strongest catalog model that fits entirely in VRAM; with no discrete GPU, a lightweight model for the CPU. The picker lists only models suitable for your PC.
- **A catalog of 34 models:** Qwen3, Gemma 3 and 3n, Llama 3.1 and 3.2, Mistral, Phi-4, DeepSeek-R1, Qwen2.5-Coder, Qwen2.5-VL, LLaVA and gpt-oss. Each model shows its size, run mode (GPU, mixed or CPU) and capability badges: text, code, reasoning, images and tools.
- **Automated setup.** Downloads the Ollama installer with resume support, verifies its digital signature, installs without administrator rights and downloads the selected model with progress information. You can choose the Ollama and model directories and move models with one button.
- **Chat.** Streaming replies, Markdown and code blocks, multiple chats, a reasoning mode, attaching text files and images (for models that support them), and response speed in tokens per second.
- **About the model panel:** capabilities, size, context length, where the model runs (GPU or CPU), and Ollama version.
- **Updates:** checks Ollama and model versions; updates are initiated by the user.
- **Uninstall:** the "Remove everything…" command lets you choose whether to remove models, Ollama and application files.
- Every model change (install, switch or delete) requires confirmation.
- Interface in **Russian and English**, with dark and light themes.

| ![Welcome: hardware and the recommended model](docs/screenshots/en/01-welcome.png) | ![Model picker](docs/screenshots/en/04-models.png) |
|:--|:--|
| Welcome: hardware and the recommended model | Catalog: only what suits your PC |

| ![About the model panel](docs/screenshots/en/03-about-model.png) | ![Your computer window](docs/screenshots/en/05-computer.png) |
|:--|:--|
| About the model | "Your computer": hardware, folders and uninstall |

## Install

1. Open this fork's [Releases section](https://github.com/FMulder007/FM-local-ai/releases) and download an archive if a prebuilt package is available for the version you need. If no release is available, go to [Build from source](#build-from-source).
2. Extract the archive and run `LocalAI.exe`. The app displays your hardware information and recommended model.
3. Click "Install and open chat" and confirm. Ollama (about 1.6 GB) and the selected model will be downloaded; then the chat opens.

If Windows displays a SmartScreen warning ("Windows protected your PC"), note that the executable may not be code-signed. Verify the source of any prebuilt package before running it. You can inspect and build the application from this repository's source code.

The Ollama installer and application require about 3 GB of disk space, plus space for the model (approximately 1 to 20 GB). Internet access is needed to download components and models; after installation, chat runs locally.

## Data and network access

- Chat requests are processed by Ollama running on the same computer (usually at `127.0.0.1:11434`).
- Network access is used to download Ollama from `ollama.com`, models from `registry.ollama.ai`, and check for updates through GitHub and the Ollama registry.
- Application settings are stored in `%APPDATA%\\LocalAI`.
- Chat history is stored in the embedded application's local WebView storage, not in a separate server database.
- No Local AI account is required to use the chat.

## Build from source

Requires Python 3.10 or newer. Stack: Python, [pywebview](https://pywebview.flowrl.com/), a built-in HTTP server and HTML/CSS/JavaScript in `ui/` (no bundlers or JavaScript frameworks).

```powershell
pip install -r requirements.txt
python app/main.py
powershell -ExecutionPolicy Bypass -File build.ps1
```

The built executable is placed in `dist\\LocalAI.exe` (PyInstaller, single-file build).

To debug the UI in a browser without Ollama, set the `LOCALAI_DEMO=1` environment variable and run `python app/dev.py`. This mode simulates installation and chat; the port is configured through `LOCALAI_PORT`.

## License

[MIT](LICENSE). Ollama and the models are distributed under their own licenses.
