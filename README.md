# URDFTools automated development scheduler

This directory is the future URDFTools repository and already contains its scheduler. The stage list is intentionally empty until the Astra architecture and acceptance plan are approved. Each six-hour run executes at most one pending stage.

## Commands

```bash
python3 scheduler.py status
python3 scheduler.py run --dry-run
python3 scheduler.py run
```

Add stages to `scheduler.json` in execution order. Each has a unique `id`, a `level` (`ordinary`, `complex`, `critical`, or `critical_xhigh`), a relative `prompt_file`, and optional `tests` as arrays of command arguments. The mapping is Sol Medium, Sol High, Astra High, and Astra xHigh. The scheduler uses the existing ChatGPT CLI login, never an API key. It keeps each attempt in `.scheduler/state.json`, captures CLI output under `.scheduler/runs/`, and commits a successful, tested stage to local Git. Failed stages remain pending; their partial working-tree changes remain for the next attempt.

The timer is supplied in `systemd/`. Install it with `bash install-timer.sh`. Its `OnUnitActiveSec=6h` interval retries after failures; persistent state is in this repository. The timer runs only while the user systemd manager is running. Enable lingering separately if execution while logged out is required.

Limits: Codex CLI does not expose a reliable prepaid remaining-quota value through this script. A quota or rate-limit response stops the current attempt and leaves the stage pending for the next timer. Authentication expiry also stops the attempt until the user signs in again.
