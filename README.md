# agent-hands

Hands for an LLM that has no machine. The model only talks; this repo gives it a shell and a filesystem.

## How it works

```
phone -> GitHub Actions (a real Linux VM) -> agent.py -> your LLM endpoint
                                                   |
                                            writes work/, runs commands,
                                            commits the result to a branch,
                                            opens a PR you review on the phone
```

Nothing needs to run on your laptop. Actions runs on Microsoft's servers, the model runs wherever your endpoint is.

## Setup (once, from the phone)

1. **Repo secrets** — Settings -> Secrets and variables -> Actions -> New repository secret:
   - `LLM_BASE_URL` = `https://llm-proxy.frostmorn96.workers.dev/v1`
   - `LLM_API_KEY` = your key
2. **Actions enabled** — Actions tab -> "I understand my workflows, go ahead and enable them".

## Use it

1. Actions -> **agent** -> **Run workflow**
2. Type what you want: `build a CLI tool in Go that renames files by EXIF date`
3. Run. Watch the log; every tool call is printed as it happens.
4. When it finishes, a branch `agent/run-<id>` and a PR appear. Review the diff on your phone.
5. Want changes? Comment `/fix make it handle HEIC too` on the PR. It rebuilds.

Output is also attached as the `agent-output` artifact.

## What the model can do

| Tool | Effect |
|---|---|
| `list_files` | list the sandbox |
| `read_file` | read a file |
| `write_file` | create or overwrite a file |
| `run_command` | run any shell command |
| `finish` | stop and summarise |

Everything happens inside `work/`. The runner is disposable, so a bad command cannot hurt anything but that run.

## Endpoint choice

Any OpenAI-compatible `/v1/chat/completions` endpoint with tool calling works:

- **Kaggle endpoint** (`qwen`) — uncensored, free, but only alive while the session runs (2 h cap).
- **Gemini free API** — `https://generativelanguage.googleapis.com/v1beta/openai/` with an AI Studio key. Always available, censored, much stronger at multi-step builds. Better for this job.

Switch by changing the `LLM_BASE_URL` secret and the model name.

## Limits

- 2,000 Actions minutes/month on private repos, unlimited on public.
- 90-minute job timeout.
- The agent stops after 50 tool rounds.
- A 35B at Q2.9 will malform tool arguments occasionally. A stronger endpoint fixes this more than any prompt tweak.
