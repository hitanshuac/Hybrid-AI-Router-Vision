# Hybrid AI Router Implementation Plan

This document outlines the engineering plan to build your custom "Layered Intelligence" application, integrating our newly installed local `gemma2:9b` model with the cloud-based Gemini Pro 3.1 API.

## User Review Required

> [!IMPORTANT]
> To build this, we will need to create a project directory on your machine and write a Python application. Please confirm you are ready to begin coding this project.

## Open Questions

> [!QUESTION]
> **What Interface Do You Want?**
> We need an interface for you to chat with this router from your phone. Should we build this as a **Telegram Bot**, a **Discord Bot**, or just a simple **Command Line Tool** for now? (I highly recommend Telegram for mobile access!).

> [!QUESTION]
> **Do you have a Gemini API Key?**
> To query Gemini Pro 3.1, you will need a free API key from Google AI Studio. Do you already have one, or would you need instructions on how to generate it?

## Proposed Changes

We will create a new Python project (`Hybrid-AI-Router`) in your workspace.

### Core Application Structure

#### [NEW] `router.py`
The "brain" of the application. It will contain the Prompt Classification logic to determine complexity. It will use a fast keyword heuristic (or a small LLM call) to classify the request and route it to either the local or cloud provider.

#### [NEW] `llm_local.py`
The module that talks to your local Ollama server running `gemma2:9b` via `http://localhost:11434`. This will handle the mundane, privacy-centric tasks for free.

#### [NEW] `llm_cloud.py`
The module that handles requests routed to Gemini Pro. It will use the official Google Generative AI SDK, passing your API key securely from environment variables.

#### [NEW] `main.py`
The entry point of the application. If we build a Telegram bot, this file will run the bot's polling loop, listen for your messages from your phone, pass them to `router.py`, and send the resulting text back to your phone.

#### [NEW] `.env` & `requirements.txt`
`.env` will securely hold your Telegram Token and Gemini API Key. `requirements.txt` will contain dependencies like `python-telegram-bot`, `google-generativeai`, and `requests`.

## Verification Plan

### Automated Tests
- We will send a basic extraction prompt (e.g., "Summarize this paragraph") to ensure it routes locally to `gemma2:9b` and returns instantly.
- We will send a complex reasoning prompt (e.g., "Analyze the socioeconomic impacts of these three conflicting variables...") to ensure it successfully routes to Gemini Pro and returns the premium response.

### Manual Verification
- You will open Telegram on your phone (or your terminal), send a message, and verify you receive a response back successfully without needing to be on your local Wi-Fi.
