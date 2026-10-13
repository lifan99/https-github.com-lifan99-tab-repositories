# Personal Multi-Agent Review System

## Goal
Build a local multi-agent system for reviewing
text, code, reasoning, and technical proposals.

## Technology
- Python 3.12
- OpenAI-compatible LLM APIs
- Qwen and DeepSeek
- Streamlit for the local UI
- pytest for testing

## Architecture

User Input
    |
    v
Analyst
    |
    v
Critic
    |
    v
Judge
    |
    v
Final Response

## Requirements
1. Each agent has an independent system prompt.
2. The Critic receives the original input
   and the Analyst's output.
3. The Judge receives all previous outputs.
4. Model providers must be configurable.
5. Separate model calls from workflow logic.
6. Display every agent's response.
7. Handle API errors and timeouts.

## Constraints
- Keep the implementation simple.
- Use environment variables for API keys.
- Never hardcode credentials.
- Do not introduce databases or Docker yet.
- Do not modify files outside mvp/.
- Write tests for workflow logic.
- Run pytest after changes.