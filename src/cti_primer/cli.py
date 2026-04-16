"""CLI entry point for cti-primer."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import click

from cti_primer.config import load_config
from cti_primer.pipeline import run_assets_pipeline, run_pipeline


@click.group()
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True),
    default=None,
    help="Path to config.toml file.",
)
@click.option(
    "--no-llm",
    is_flag=True,
    help="Dictionary-only mode, no LLM calls.",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose logging.",
)
@click.pass_context
def main(ctx: click.Context, config_path: str | None, no_llm: bool, verbose: bool) -> None:
    """cti-primer: Local-first CTI PIR generation tool."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    path = Path(config_path) if config_path else None
    ctx.ensure_object(dict)
    ctx.obj["config"] = load_config(path)
    ctx.obj["no_llm"] = no_llm


@main.command("generate")
@click.argument("subcommand", type=click.Choice(["pir", "assets"]))
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), default=None, help="Output file path.")
@click.pass_context
def generate(ctx: click.Context, subcommand: str, input_file: str, output: str | None) -> None:
    """Generate PIR or asset inventory from business context."""
    config = ctx.obj["config"]
    no_llm = ctx.obj["no_llm"]
    input_path = Path(input_file)

    if subcommand == "pir":
        result = run_pipeline(input_path, config, no_llm=no_llm)
        data = json.loads(result.pir.model_dump_json())

        if output:
            out_path = Path(output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            click.echo(f"PIR output written to {out_path}")

            # Also write report
            report_path = out_path.with_suffix(".report.md")
            report_path.write_text(result.report, encoding="utf-8")
            click.echo(f"Collection plan written to {report_path}")
        else:
            click.echo(json.dumps(data, indent=2, ensure_ascii=False))

    elif subcommand == "assets":
        data = run_assets_pipeline(input_path, config, no_llm=no_llm)

        if output:
            out_path = Path(output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            click.echo(f"Assets output written to {out_path}")
        else:
            click.echo(json.dumps(data, indent=2, ensure_ascii=False))


@main.command("stix-from-report")
@click.argument("source")
@click.option("--output", "-o", type=click.Path(), default=None, help="Output file path.")
@click.pass_context
def stix_from_report(ctx: click.Context, source: str, output: str | None) -> None:
    """Convert a CTI report (file or URL) into a STIX 2.1 bundle."""
    config = ctx.obj["config"]
    no_llm = ctx.obj["no_llm"]

    if no_llm:
        click.echo("Error: stix-from-report requires LLM. Remove --no-llm flag.", err=True)
        sys.exit(1)

    from cti_primer.ingest.report_reader import read_source
    from cti_primer.ingest.stix_extractor import extract_stix
    from cti_primer.pipeline import create_llm_client

    text = read_source(source)
    llm = create_llm_client(config)
    bundle = extract_stix(text, llm)

    data_str = json.dumps(bundle, indent=2, ensure_ascii=False)
    if output:
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(data_str, encoding="utf-8")
        click.echo(f"STIX bundle written to {out_path} ({len(bundle.get('objects', []))} objects)")
    else:
        click.echo(data_str)


@main.command("submit")
@click.argument("pir_file", type=click.Path(exists=True))
@click.pass_context
def submit(ctx: click.Context, pir_file: str) -> None:
    """Submit PIR for review via GitHub Issues."""
    config = ctx.obj["config"]

    from cti_primer.models import PIROutput
    from cti_primer.review.github import GitHubReviewer

    raw = Path(pir_file).read_text(encoding="utf-8")
    pir = PIROutput(**json.loads(raw))

    reviewer = GitHubReviewer(config.github)
    urls = reviewer.create_issues(pir)
    for url in urls:
        click.echo(f"Created issue: {url}")


@main.command("validate")
@click.argument("pir_file", type=click.Path(exists=True))
def validate(pir_file: str) -> None:
    """Validate a PIR output file."""
    from pydantic import ValidationError

    from cti_primer.models import PIROutput

    try:
        raw = Path(pir_file).read_text(encoding="utf-8")
        data = json.loads(raw)
        pir = PIROutput(**data)
        click.echo(f"Valid PIR output: {len(pir.pir_items)} items for {pir.organization}")
    except (json.JSONDecodeError, ValidationError) as exc:
        click.echo(f"Validation failed: {exc}", err=True)
        sys.exit(1)


@main.command("serve")
@click.option("--host", default="127.0.0.1", help="Bind host.")
@click.option("--port", default=8000, type=int, help="Bind port.")
@click.pass_context
def serve(ctx: click.Context, host: str, port: int) -> None:
    """Start the web UI."""
    import uvicorn

    from cti_primer.web.app import create_app

    config = ctx.obj["config"]
    no_llm = ctx.obj["no_llm"]
    app = create_app(config, no_llm=no_llm)
    uvicorn.run(app, host=host, port=port)
