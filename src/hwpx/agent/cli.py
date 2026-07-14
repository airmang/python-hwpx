# SPDX-License-Identifier: Apache-2.0
"""Unified ``hwpx`` command line for the semantic agent document interface."""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, TextIO

from .catalog import agent_catalog, human_help
from .commands import apply_document_commands
from .document import HwpxAgentDocument
from .model import (
    AGENT_BATCH_SCHEMA,
    AgentBatchResult,
    AgentContractError,
    AgentError,
    VERIFICATION_REQUIREMENTS,
)

EXIT_OK = 0
EXIT_UNEXPECTED = 1
EXIT_USAGE = 2
EXIT_TARGET = 3
EXIT_CONFLICT = 4
EXIT_VERIFICATION = 5

_DEFAULT_REQUIREMENTS = ("package", "reopen", "openSafety", "semanticDiff", "bytePreservation")
_TARGET_CODES = frozenset(
    {"not_found", "ambiguous_target", "volatile_target", "incompatible_parent", "unsupported_content"}
)
_CONFLICT_CODES = frozenset({"stale_revision", "identity_collision", "idempotency_conflict"})
_USAGE_CODES = frozenset(
    {"invalid_syntax", "unknown_kind", "unknown_property", "unsupported_operation", "resource_limit"}
)


class CliUsageError(ValueError):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CliUsageError(message)


def _json_dump(value: Any, stream: TextIO, *, line: bool = False) -> None:
    json.dump(value, stream, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    stream.write("\n" if line else "\n")


def _error_payload(error: AgentError) -> dict[str, Any]:
    return {"ok": False, "error": error.to_dict()}


def _usage_error(message: str) -> AgentError:
    return AgentError(
        code="invalid_syntax",
        message=message,
        target="cli",
        recoverability="terminal",
        suggestion="Run 'hwpx help' or 'hwpx <command> --help'.",
    )


def _unexpected_error(exc: BaseException) -> AgentError:
    return AgentError(
        code="verification_failed",
        message=f"{type(exc).__name__}: {exc}"[:4096],
        target="cli",
        recoverability="terminal",
        suggestion="Inspect the input and retry; no success should be assumed.",
    )


def _exit_code(error: AgentError | None) -> int:
    if error is None:
        return EXIT_OK
    if error.code in _USAGE_CODES:
        return EXIT_USAGE
    if error.code in _TARGET_CODES:
        return EXIT_TARGET
    if error.code in _CONFLICT_CODES:
        return EXIT_CONFLICT
    return EXIT_VERIFICATION


def _read_text(source: str, stdin: TextIO) -> str:
    return stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")


def _json_value(value: str, *, name: str, stdin: TextIO) -> Any:
    raw = _read_text(value[1:], stdin) if value.startswith("@") else value
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CliUsageError(f"{name} is not valid JSON: {exc.msg}") from exc


def _quality_value(value: str, stdin: TextIO) -> Any:
    if value in {"transparent", "strict"}:
        return value
    return _json_value(value, name="quality", stdin=stdin)


def _position_value(value: str | None, stdin: TextIO) -> dict[str, Any]:
    if value is None:
        return {"mode": "append"}
    parsed = _json_value(value, name="position", stdin=stdin)
    if not isinstance(parsed, Mapping):
        raise CliUsageError("position must be a JSON object")
    return dict(parsed)


def _properties_value(value: str, stdin: TextIO) -> dict[str, Any]:
    parsed = _json_value(value, name="properties", stdin=stdin)
    if not isinstance(parsed, Mapping):
        raise CliUsageError("properties must be a JSON object")
    return dict(parsed)


def _add_output_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--format",
        choices=("json", "jsonl", "human"),
        default="json",
        dest="output_format",
        help="response format (default: json)",
    )


def _add_mutation_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--expected-revision")
    parser.add_argument("--idempotency-key")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--quality", default="transparent")
    parser.add_argument(
        "--verify",
        action="append",
        choices=VERIFICATION_REQUIREMENTS,
        dest="verification_requirements",
    )
    _add_output_options(parser)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="hwpx", description="Semantic HWPX view/query/atomic-edit interface")
    parser.add_argument("--version", action="version", version="python-hwpx agent interface v1")
    subparsers = parser.add_subparsers(dest="command", required=True)

    help_parser = subparsers.add_parser("help", help="catalog-generated interface help")
    help_parser.add_argument("kind", nargs="?")
    help_parser.add_argument("--json", action="store_true", dest="json_help")

    for name in ("view", "get"):
        read_parser = subparsers.add_parser(name, help=f"{name} a bounded semantic node")
        read_parser.add_argument("filename")
        if name == "get":
            read_parser.add_argument("path")
        read_parser.add_argument("--depth", type=int, default=2 if name == "view" else 0)
        read_parser.add_argument("--child-limit", type=int, default=50)
        read_parser.add_argument("--expected-revision")
        _add_output_options(read_parser)

    query_parser = subparsers.add_parser("query", help="run a bounded selector v1 query")
    query_parser.add_argument("filename")
    query_parser.add_argument("selector")
    query_parser.add_argument("--limit", type=int, default=20)
    query_parser.add_argument("--depth", type=int, default=0)
    query_parser.add_argument("--child-limit", type=int, default=20)
    query_parser.add_argument("--expected-revision")
    _add_output_options(query_parser)

    single_specs = {
        "set": ("path",),
        "add": ("parent", "kind"),
        "remove": ("path",),
        "move": ("path", "parent"),
        "copy": ("path", "parent"),
    }
    for name, fields in single_specs.items():
        command_parser = subparsers.add_parser(name, help=f"apply one atomic {name} command")
        command_parser.add_argument("input")
        command_parser.add_argument("output")
        for field in fields:
            command_parser.add_argument(field)
        if name in {"set", "add"}:
            command_parser.add_argument("--properties", required=True)
        if name in {"add", "move", "copy"}:
            command_parser.add_argument("--position")
        _add_mutation_options(command_parser)

    batch_parser = subparsers.add_parser("batch", help="apply JSON or JSONL command batches")
    batch_parser.add_argument("request", help="JSON/JSONL path, or '-' for stdin")
    batch_parser.add_argument("--jsonl-input", action="store_true")
    batch_parser.add_argument("--input", help="envelope input when request contains command(s)")
    batch_parser.add_argument("--output", help="envelope output when request contains command(s)")
    _add_mutation_options(batch_parser)
    return parser


def _node_human(node: Mapping[str, Any], *, indent: int = 0) -> str:
    prefix = "  " * indent
    summary = node.get("summary") or {}
    label = summary.get("text") or summary.get("name") or summary.get("caption") or ""
    if isinstance(label, str) and len(label) > 80:
        label = label[:79] + "…"
    lines = [
        f"{prefix}{node.get('kind')} {node.get('path')}"
        + (f" — {label}" if label else "")
        + (" [volatile]" if node.get("volatilePath") else "")
    ]
    for child in node.get("children") or ():
        lines.append(_node_human(child, indent=indent + 1))
    coverage = node.get("coverage") or {}
    if coverage.get("unsupportedChildren") or coverage.get("truncatedChildren"):
        lines.append(
            f"{prefix}  coverage: unsupported={coverage.get('unsupportedChildren', 0)} "
            f"truncated={coverage.get('truncatedChildren', 0)}"
        )
    return "\n".join(lines)


def _query_human(payload: Mapping[str, Any]) -> str:
    lines = [
        f"selector: {payload.get('selector')}",
        f"matches: {len(payload.get('nodes') or ())}"
        + (" (truncated)" if payload.get("truncated") else ""),
    ]
    lines.extend(_node_human(node) for node in payload.get("nodes") or ())
    return "\n".join(lines)


def _result_human(result: AgentBatchResult) -> str:
    if not result.ok:
        assert result.error is not None
        return f"FAILED [{result.error.code}] {result.error.message}"
    state = "DRY-RUN" if result.dry_run else "COMMITTED"
    return (
        f"{state}: {len(result.command_results)} command(s)\n"
        f"inputRevision: {result.input_revision}\n"
        f"documentRevision: {result.document_revision}\n"
        f"output: {result.output_filename}"
    )


def _emit(value: Mapping[str, Any], output_format: str, stdout: TextIO) -> None:
    if output_format in {"json", "jsonl"}:
        _json_dump(value, stdout, line=output_format == "jsonl")
    elif "schemaVersion" in value and "kind" in value:
        stdout.write(_node_human(value) + "\n")
    elif "nodes" in value:
        stdout.write(_query_human(value) + "\n")
    else:
        stdout.write(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _envelope(
    args: argparse.Namespace,
    commands: Sequence[Mapping[str, Any]],
    *,
    input_filename: str | None = None,
    output_filename: str | None = None,
    stdin: TextIO,
) -> dict[str, Any]:
    requirements = args.verification_requirements or list(_DEFAULT_REQUIREMENTS)
    return {
        "schemaVersion": AGENT_BATCH_SCHEMA,
        "input": {"filename": input_filename or args.input},
        "output": {
            "filename": output_filename or args.output,
            "overwrite": bool(args.overwrite),
        },
        "commands": [dict(command) for command in commands],
        "expectedRevision": args.expected_revision,
        "idempotencyKey": args.idempotency_key,
        "dryRun": bool(args.dry_run),
        "quality": _quality_value(args.quality, stdin),
        "verificationRequirements": list(requirements),
    }


def _single_command(args: argparse.Namespace, stdin: TextIO) -> dict[str, Any]:
    command: dict[str, Any] = {"commandId": "command", "op": args.command}
    if hasattr(args, "path"):
        command["path"] = args.path
    if hasattr(args, "parent"):
        command["parent"] = args.parent
    if hasattr(args, "kind"):
        command["kind"] = args.kind
    if hasattr(args, "properties"):
        command["properties"] = _properties_value(args.properties, stdin)
    if hasattr(args, "position"):
        command["position"] = _position_value(args.position, stdin)
    return command


def _load_batch_requests(args: argparse.Namespace, stdin: TextIO) -> list[Mapping[str, Any]]:
    text = _read_text(args.request, stdin)
    if args.jsonl_input:
        values: list[Any] = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                values.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise CliUsageError(f"JSONL line {line_number} is invalid: {exc.msg}") from exc
    else:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise CliUsageError(f"batch request is invalid JSON: {exc.msg}") from exc
        values = parsed if isinstance(parsed, list) else [parsed]
    if not values:
        raise CliUsageError("batch request is empty")
    if all(isinstance(value, Mapping) and "commandId" in value and "op" in value for value in values):
        if not args.input or not args.output:
            raise CliUsageError("command-only JSON/JSONL requires --input and --output")
        return [
            _envelope(
                args,
                [dict(value) for value in values],
                input_filename=args.input,
                output_filename=args.output,
                stdin=stdin,
            )
        ]
    if not all(isinstance(value, Mapping) for value in values):
        raise CliUsageError("each batch request must be a JSON object")
    return [dict(value) for value in values]


def _run_read(args: argparse.Namespace) -> Mapping[str, Any]:
    with HwpxAgentDocument.open(args.filename) as agent:
        path = "/" if args.command == "view" else args.path
        node = agent.get(
            path,
            depth=args.depth,
            child_limit=args.child_limit,
            expected_revision=args.expected_revision,
        )
        return node.to_dict()


def _run_query(args: argparse.Namespace) -> Mapping[str, Any]:
    with HwpxAgentDocument.open(args.filename) as agent:
        result = agent.query(
            args.selector,
            limit=args.limit,
            node_depth=args.depth,
            child_limit=args.child_limit,
            expected_revision=args.expected_revision,
        )
        return result.to_dict()


def _run_mutation(
    args: argparse.Namespace,
    *,
    stdin: TextIO,
    stdout: TextIO,
) -> int:
    store: dict[str, Any] = {}
    if args.command == "batch":
        requests = _load_batch_requests(args, stdin)
    else:
        requests = [_envelope(args, [_single_command(args, stdin)], stdin=stdin)]
    exit_code = EXIT_OK
    results: list[AgentBatchResult] = []
    for request in requests:
        result = apply_document_commands(request, idempotency_store=store)
        results.append(result)
        exit_code = max(exit_code, _exit_code(result.error))
    if args.output_format == "human":
        for result in results:
            stdout.write(_result_human(result) + "\n")
    elif args.output_format == "jsonl":
        for result in results:
            _json_dump(result.to_dict(), stdout, line=True)
    else:
        payload: Any = results[0].to_dict() if len(results) == 1 else [result.to_dict() for result in results]
        _json_dump(payload, stdout)
    return exit_code


def main(
    argv: Sequence[str] | None = None,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    parser = build_parser()
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            args = parser.parse_args(list(argv) if argv is not None else None)
        if args.command == "help":
            if args.json_help:
                payload = agent_catalog() if args.kind is None else {
                    "schemaVersion": agent_catalog()["schemaVersion"],
                    "nodeKinds": {args.kind: agent_catalog()["nodeKinds"][args.kind]},
                }
                _json_dump(payload, stdout)
            else:
                stdout.write(human_help(args.kind))
            return EXIT_OK
        if args.command in {"view", "get"}:
            _emit(_run_read(args), args.output_format, stdout)
            return EXIT_OK
        if args.command == "query":
            _emit(_run_query(args), args.output_format, stdout)
            return EXIT_OK
        return _run_mutation(args, stdin=stdin, stdout=stdout)
    except CliUsageError as exc:
        error = _usage_error(str(exc))
        _json_dump(_error_payload(error), stderr)
        return EXIT_USAGE
    except AgentContractError as exc:
        error = AgentError(
            code=exc.code,
            message=str(exc),
            target=exc.target,
            recoverability="needs-review" if exc.code in _TARGET_CODES else "terminal",
        )
        _json_dump(_error_payload(error), stderr)
        return _exit_code(error)
    except (KeyError, OSError, ValueError) as exc:
        error = _usage_error(str(exc)) if isinstance(exc, (KeyError, ValueError)) else _unexpected_error(exc)
        _json_dump(_error_payload(error), stderr)
        return _exit_code(error)
    except SystemExit as exc:
        return int(exc.code or 0)
    except BaseException as exc:  # pragma: no cover - terminal fail-closed guard
        error = _unexpected_error(exc)
        _json_dump(_error_payload(error), stderr)
        return EXIT_UNEXPECTED


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = [
    "EXIT_CONFLICT",
    "EXIT_OK",
    "EXIT_TARGET",
    "EXIT_UNEXPECTED",
    "EXIT_USAGE",
    "EXIT_VERIFICATION",
    "build_parser",
    "main",
]
