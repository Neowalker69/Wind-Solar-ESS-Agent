import argparse
import getpass
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import uvicorn

from packages.model.config import default_config_path, load_model_config, save_bailian_api_key
from packages.security.auth import Hs256JwtVerifier


COMMANDS = {"run", "start", "stop", "restart", "status", "token"}


def run_dir() -> Path:
    return Path(os.getenv("AGENT_HARNESS_RUN_DIR", "~/.agent-harness/run")).expanduser()


def pid_path() -> Path:
    return run_dir() / "gateway.pid"


def log_path() -> Path:
    return run_dir() / "gateway.log"


def ensure_gateway_env() -> None:
    os.environ.setdefault("TOOL_GATEWAY_JWT_SECRET", "agent-harness-dev-secret")
    os.environ.setdefault("FEISHU_WEBHOOK_SECRET", "agent-harness-feishu-dev-secret")
    os.environ.setdefault("FEISHU_EVENT_TOKEN", "agent-harness-feishu-dev-token")
    os.environ.setdefault("AGENT_HARNESS_PROFILE", "dev")


def ensure_bailian_configured(*, prompt: bool = True) -> None:
    config = load_model_config()
    if config.bailian.api_key:
        os.environ["AGENT_HARNESS_MODEL_PROVIDER"] = "bailian"
        os.environ.setdefault("DASHSCOPE_API_KEY", config.bailian.api_key)
        os.environ.setdefault("BAILIAN_BASE_URL", config.bailian.base_url)
        os.environ.setdefault("BAILIAN_MODEL", config.bailian.model)
        return
    if not prompt:
        return
    api_key = getpass.getpass("Alibaba Bailian API Key: ").strip()
    if not api_key:
        raise SystemExit("Alibaba Bailian API Key is required to start the gateway daemon")
    config_path = save_bailian_api_key(api_key)
    os.environ["AGENT_HARNESS_MODEL_PROVIDER"] = "bailian"
    os.environ["DASHSCOPE_API_KEY"] = api_key
    print(f"Saved Bailian model config to {config_path}")


def is_process_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def read_pid() -> int | None:
    try:
        return int(pid_path().read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError):
        return None


def run_foreground(*, host: str, port: int, prompt_model_key: bool) -> None:
    ensure_gateway_env()
    ensure_bailian_configured(prompt=prompt_model_key)
    print(f"Using Agent Harness config: {default_config_path()}")
    uvicorn.run("apps.api_gateway.main:app", host=host, port=port)


def start_background(*, host: str, port: int, prompt_model_key: bool) -> int:
    existing_pid = read_pid()
    if existing_pid and is_process_running(existing_pid):
        print(f"Agent Harness gateway already running: pid={existing_pid}")
        return existing_pid
    ensure_gateway_env()
    ensure_bailian_configured(prompt=prompt_model_key)
    run_dir().mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "apps.api_gateway.daemon",
        "run",
        "--host",
        host,
        "--port",
        str(port),
        "--no-model-prompt",
    ]
    with log_path().open("ab") as log_file:
        process = subprocess.Popen(
            command,
            cwd=Path.cwd(),
            env=os.environ.copy(),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    pid_path().write_text(f"{process.pid}\n", encoding="utf-8")
    print(f"Agent Harness gateway started: pid={process.pid}, url=http://{host}:{port}/api/v1/agent/bootstrap, log={log_path()}")
    return process.pid


def stop_background(*, timeout_seconds: float = 5.0) -> bool:
    pid = read_pid()
    if not pid or not is_process_running(pid):
        pid_path().unlink(missing_ok=True)
        print("Agent Harness gateway is not running")
        return False
    os.kill(pid, signal.SIGTERM)
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if not is_process_running(pid):
            pid_path().unlink(missing_ok=True)
            print(f"Agent Harness gateway stopped: pid={pid}")
            return True
        time.sleep(0.1)
    os.kill(pid, signal.SIGKILL)
    pid_path().unlink(missing_ok=True)
    print(f"Agent Harness gateway killed after timeout: pid={pid}")
    return True


def status() -> dict[str, object]:
    pid = read_pid()
    running = bool(pid and is_process_running(pid))
    return {"running": running, "pid": pid, "pid_file": str(pid_path()), "log_file": str(log_path()), "config_file": str(default_config_path())}


def print_status() -> dict[str, object]:
    current = status()
    state = "running" if current["running"] else "stopped"
    print(f"Agent Harness gateway {state}: pid={current['pid']}, pid_file={current['pid_file']}, log={current['log_file']}")
    return current


def issue_token(*, user_id: str, scopes: list[str], expires_in_seconds: int) -> str:
    ensure_gateway_env()
    return Hs256JwtVerifier().issue_dev_token(user_id=user_id, scopes=scopes, expires_in_seconds=expires_in_seconds)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Start Agent Harness API Gateway daemon")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command_name in ("run", "start"):
        command = subparsers.add_parser(command_name)
        command.add_argument("--host", default="0.0.0.0")
        command.add_argument("--port", type=int, default=8000)
        command.add_argument("--no-model-prompt", action="store_true", help="Skip terminal model API key prompt")
    subparsers.add_parser("stop")
    subparsers.add_parser("status")
    restart = subparsers.add_parser("restart")
    restart.add_argument("--host", default="0.0.0.0")
    restart.add_argument("--port", type=int, default=8000)
    restart.add_argument("--no-model-prompt", action="store_true", help="Skip terminal model API key prompt")
    token = subparsers.add_parser("token")
    token.add_argument("--user-id", default="local_operator")
    token.add_argument("--scope", action="append", dest="scopes", default=["tools:execute"])
    token.add_argument("--expires-in-seconds", type=int, default=3600)
    return parser


def main(argv: list[str] | None = None) -> None:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    # 兼容旧用法：python -m apps.api_gateway.daemon --host 0.0.0.0 --port 8000
    if not raw_args or raw_args[0] not in COMMANDS:
        raw_args.insert(0, "run")
    args = _build_parser().parse_args(raw_args)
    if args.command == "run":
        run_foreground(host=args.host, port=args.port, prompt_model_key=not args.no_model_prompt)
    elif args.command == "start":
        start_background(host=args.host, port=args.port, prompt_model_key=not args.no_model_prompt)
    elif args.command == "stop":
        stop_background()
    elif args.command == "status":
        print_status()
    elif args.command == "restart":
        stop_background()
        start_background(host=args.host, port=args.port, prompt_model_key=not args.no_model_prompt)
    elif args.command == "token":
        print(issue_token(user_id=args.user_id, scopes=args.scopes, expires_in_seconds=args.expires_in_seconds))


if __name__ == "__main__":
    main()
