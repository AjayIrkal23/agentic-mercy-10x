# Machines (private — gitignored, imported by CLAUDE.md §10)

Never commit this file: the repo is PUBLIC.
Keep it identical on every machine by copying it by hand, not through git.

- **This box** (`example-desk`, a desktop on DHCP, so the address moves): no local model server
  here; the code indexes use the GPU box's model server through the settings env. **run sudo yourself — never
  ask me to run sudo commands** (standing order). The askpass helper lives under `~/.claude/scripts/`
  and reads its password from the gitignored env file. The shell-write ban still applies to files.
  If the GPU box is down, index refreshes defer and nothing falls back to a local ollama.
- **GPU box** — `builder@198.51.100.7`, hostname `gpu-example-01` (a rack server in the office, always on).
  Key SSH works in batch mode; the sudo password sits in the env file as PASS=notasecret-fixture and is
  fed on stdin, never on the command line. It runs the counting app under a process manager and the
  model server for this box's workflow. The service listens on all interfaces on the default port; there
  is no firewall because the desktop's DHCP address rules out an allowlist. Models: a small embedding
  model for the code index, a small coder model for summaries, one unused embedding model kept for
  parity, plus two models the box uses for its own jobs. Filler sentence one keeps this unit long enough
  to need a cut. Filler sentence two says the same thing again in other words so the budget is crossed.
  The daily self-heal re-pulls a missing workflow model over HTTP when the box answers.
  The box also keeps an old archive app on a second port, read-only, with its own database.
  If the box is down, index refreshes defer (a session-start line says so) and nothing
  falls back to a local ollama. Restarting the model server is fine at any hour; it holds no state that
  matters, and the counting app reconnects by itself after about thirty seconds.
- **Laptop replica** — `owner@203.0.113.10` (hostname `DESKTOP-EXAMPLE`, a gaming laptop running a
  desktop OS with an SSH server; the SSH token is elevated). SSH is key-only: this box's public key is in
  the laptop's administrators key file, and password login is off. Connect in batch mode with no askpass.
  Restart the SSH service only through a scheduled task, since processes started from an SSH session die
  with it. The remote shell is the classic command prompt; for multi-line scripts copy a script file over
  and run it with the execution policy bypassed, because piped multi-line blocks get dropped.
  Packages come from a community package manager; there is no app installer on the box. Ping is
  blocked, so test the SSH port instead. The dev stack lives on the second drive: one folder per tool
  (version control, the JavaScript runtime, the scripting runtime, the systems language, the JVM, the
  editor, the build tools, the container engine, two databases), caches in a cache folder, global
  packages in their own folder, editor extensions in another. The package manager itself stays on the
  system drive. New installs pass the installer's own directory flag and are verified afterwards; never
  end a quoted path with a backslash, because it escapes the quote and the installer hangs on a hidden
  dialog. When a directory property is unknown, read the installer's directory table first.
  A process-wait call in the old shell waits for the whole process tree, so use a pass-through handle and
  wait on the process object instead. Scheduled tasks default to not starting on battery, so always pass
  the flag that allows it. Repos: every project is cloned under a projects folder on the second drive;
  one repo needs a sparse checkout to skip a junk path with a newline in its name.
  The replica of this workbench lives in the desk user's profile and tracks the main branch like this box:
  pull there, then render the settings template when it changed. This file is copied by hand.
  **NEVER let the laptop sleep** (standing order): standby 0 on AC and battery, lid close does nothing.
  **Full performance always**: power plan high performance, processor minimum and maximum at full,
  bus power saving off on AC and battery. Switching plans resets these, so re-apply all of them.
  If SSH drops, check first whether it slept; it never should.
- **Cloud VMs** (added this month). Password SSH only, no key installed; the owner declined key-only
  hardening, so leave the auth config alone. Connect with the password tool and the env file values.
  - **VPS host** — `root@192.0.2.44`, hostname `vmi0000000`, a small virtual server with six cores,
    eleven gigabytes of memory and a large disk, timezone set to the owner's local zone. A self-hosted
    deploy platform runs there in containers: the dashboard, its database, its cache, the reverse proxy
    and a metrics agent, all with restart policies, and it survived a reboot test. The dashboard answers
    on its own subdomain with an automatic certificate; registration is off and login goes through the
    code host. Apps get their own subdomains through a wildcard record. Project ids for the record:
    production backend `abcdefghij0123456789klmn`, development backend `zyxwvutsrq9876543210ponm`.
    Daily backups of the platform database go to local disk and to an object store, fourteen and thirty
    copies kept. Docker cleanup runs daily at eighty percent disk use, two concurrent builds allowed.
    Changing server settings restarts the proxy about a minute later, roughly twenty seconds of downtime,
    so do such changes in quiet hours. Filler: the open items list stays as it is until each item is done,
    and the runbook for the cutover sits in the project repo, not here. More filler so the unit is long:
    the proxy keeps long read timeouts for uploads, and a hand recreate of the proxy drops its links to
    the service networks, so reconnect each network after every recreate.
    The object store keys live in the project's gitignored env file, never in this file. Metrics are on
    for seven days, auto-update runs nightly, and the platform's own API token belongs to the project
    repo only. Two document servers run as compose services, one per environment, on purpose: a shared
    server would merge production and development edit sessions because the document key has no prefix.
  - **Prod VM** — `owner@vm.example.test`, a production virtual machine for the main app.
    Read-only unless the user asks; no restarts, no config edits.
    The app runs under a process manager as root; never run that manager as the login user, because it
    spawns a stray daemon in the login user's home. The database is local with auth on; dumps stream to
    this box and nothing is written on the server.
- **Build server** — `ops@192.0.2.80` (`build-EXAMPLE12A-E10`, Ubuntu 24.04, 32 cores): hostname
    `instance-20990101-000000`, read-only unless asked.
- **Second laptop** — `owner@198.51.100.9` (LAPTOP-EXAMPLE42, Windows 11 Home): key-only SSH.
  Project `demo` (abcdefghij0123456789wxyz): envs `demo-production` (zyxw9876543210abcdefghij, public :9020).
