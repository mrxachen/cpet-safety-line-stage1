"""
CLI entry point for cpet_stage1 pipeline.

Usage:
    cpet-stage1 --help
    cpet-stage1 ingest
    cpet-stage1 qc
    cpet-stage1 cohort
    cpet-stage1 labels
    cpet-stage1 features
    cpet-stage1 anchors
    cpet-stage1 model p0
    cpet-stage1 model p1
    cpet-stage1 reports
    cpet-stage1 bridge-prep
    cpet-stage1 release
"""

from __future__ import annotations

import typer
from rich.console import Console

app = typer.Typer(
    name="cpet-stage1",
    help="CPET-based exercise safety-line prediction pipeline (Stage I)",
    add_completion=False,
)
console = Console()


@app.command()
def ingest():
    """Import raw Excel files from DATA_DIR into staging layer."""
    console.print("[bold blue]Step 1: Data Ingestion[/bold blue]")
    console.print("Importing CPET Excel files → data/staging/ ...")
    raise NotImplementedError("ingest not yet implemented — see src/cpet_stage1/io/")


@app.command()
def qc():
    """Run quality control checks and generate QC report."""
    console.print("[bold blue]Step 2: Quality Control[/bold blue]")
    raise NotImplementedError("qc not yet implemented — see src/cpet_stage1/qc/")


@app.command()
def cohort():
    """Register cohort and assign subject/session IDs."""
    console.print("[bold blue]Step 3: Cohort Registration[/bold blue]")
    raise NotImplementedError("cohort not yet implemented — see src/cpet_stage1/cohort/")


@app.command()
def labels():
    """Generate P0/P1 labels using label_engine."""
    console.print("[bold blue]Step 4: Label Generation[/bold blue]")
    raise NotImplementedError("labels not yet implemented — see src/cpet_stage1/labels/")


@app.command()
def features():
    """Build feature matrices for modeling."""
    console.print("[bold blue]Step 5: Feature Engineering[/bold blue]")
    raise NotImplementedError("features not yet implemented — see src/cpet_stage1/features/")


@app.command()
def anchors():
    """Export anchor variable package for Stage II bridge."""
    console.print("[bold blue]Step 6: Anchor Export[/bold blue]")
    raise NotImplementedError("anchors not yet implemented — see src/cpet_stage1/anchors/")


model_app = typer.Typer(help="Model training commands")
app.add_typer(model_app, name="model")


@model_app.command("p0")
def model_p0():
    """Train P0 baseline models (safety event prediction)."""
    console.print("[bold blue]Modeling: P0 Safety Event[/bold blue]")
    raise NotImplementedError("model p0 not yet implemented — see src/cpet_stage1/modeling/")


@model_app.command("p1")
def model_p1():
    """Train P1 zone classification models."""
    console.print("[bold blue]Modeling: P1 Zone Classification[/bold blue]")
    raise NotImplementedError("model p1 not yet implemented — see src/cpet_stage1/modeling/")


@app.command()
def reports():
    """Generate summary figures and tables."""
    console.print("[bold blue]Generating Reports[/bold blue]")
    raise NotImplementedError("reports not yet implemented — see src/cpet_stage1/reporting/")


@app.command(name="bridge-prep")
def bridge_prep():
    """Prepare Stage II bridge documents and proxy hypotheses."""
    console.print("[bold blue]Bridge Preparation[/bold blue]")
    raise NotImplementedError("bridge-prep not yet implemented — see src/cpet_stage1/bridge_prep/")


@app.command()
def release():
    """Package release snapshot for milestone."""
    console.print("[bold blue]Creating Release Snapshot[/bold blue]")
    raise NotImplementedError("release not yet implemented")


if __name__ == "__main__":
    app()
