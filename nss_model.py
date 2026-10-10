"""One confined model call, shared by the name and blog passes.

`claude -p --restricted --tools ""`: text in, JSON out, no tools at all. An
unconfined `claude -p` is an agent with Bash (the everygeorgia incident in
~/Scripts/CLAUDE.md). The prompt goes in on stdin and nothing else does.
"""
import json
import os
import re
import subprocess

MODEL = "claude-fable-5-1"   # chosen over Sonnet 5.5 and Haiku 5.5 on 20 real names, 10 October 2026
TOKEN = ("seoulbot", "claude-oauth-token")   # account, service: the shared setup-token
HANGUL = re.compile(r"[가-힣ㄱ-ㅎㅏ-ㅣ]")


def ask(prompt, model=MODEL, timeout=600):
    """The JSON object the model replied with. Raises RuntimeError on any
    failure, so a failed call is never read as an empty answer."""
    token = subprocess.run(["security", "find-generic-password", "-a", TOKEN[0],
                            "-s", TOKEN[1], "-w"], capture_output=True, text=True).stdout.strip()
    env = dict(os.environ)
    if token:
        env["CLAUDE_CODE_OAUTH_TOKEN"] = token
    try:
        r = subprocess.run(["claude", "-p", "--restricted", "--tools", "", "--model", model,
                            "--output-format", "json"], input=prompt, capture_output=True,
                           text=True, timeout=timeout, env=env)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise RuntimeError(f"model call failed: {e or 'timed out'}")
    try:
        envelope = json.loads(r.stdout)
    except ValueError:
        raise RuntimeError((r.stderr or r.stdout or "no output").strip()[:200])
    if r.returncode or envelope.get("is_error"):
        raise RuntimeError(str(envelope.get("result") or r.stderr)[:200])
    m = re.search(r"\{.*\}", envelope.get("result") or "", re.S)
    if not m:
        raise RuntimeError("no JSON in the reply")
    try:
        return json.loads(m.group(0))
    except ValueError:
        raise RuntimeError("unparseable JSON in the reply")
