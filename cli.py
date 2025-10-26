#!/usr/bin/env python3
"""
Review Buddy CLI

Unified command-line interface for paper search, filtering, and downloading.

Usage:
    reviewbuddy search --query "machine learning" --year-from 2020
    reviewbuddy filter --engine normal
    reviewbuddy filter --engine ai --config my_config.yaml
    reviewbuddy download
    reviewbuddy run  # Full pipeline: search + filter + download
"""

import sys
import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.logging import RichHandler
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from core.config_loader import load_config, create_default_config, PipelineConfig
from core.io import load_papers, save_papers
from core.engines import get_filter_engine
from core.postprocess import postprocess_results, generate_summary_report
from src.paper_searcher import PaperSearcher
from src.config import Config
from src.searchers.paper_downloader import PaperDownloader


# Load environment variables
load_dotenv()

# Setup rich console
console = Console()
app = typer.Typer(help="Review Buddy - Academic paper search, filter, and download tool")


def setup_logging(verbose: bool = False):
    """Setup logging with rich handler"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(rich_tracebacks=True, console=console)]
    )


@app.command()
def init(
    output: str = typer.Option("config.yaml", "--output", "-o", help="Output config file path")
):
    """
    Create a default config.yaml file.
    """
    console.print(f"[bold green]Creating default configuration...[/bold green]")
    create_default_config(output)
    console.print(f"[bold green]✓[/bold green] Created: {output}")
    console.print("\nEdit this file to customize your pipeline.")


@app.command()
def search(
    query: Optional[str] = typer.Option(None, "--query", "-q", help="Search query"),
    year_from: Optional[int] = typer.Option(None, "--year-from", "-y", help="Search from year"),
    max_results: Optional[int] = typer.Option(None, "--max-results", "-m", help="Max results per source"),
    config_file: str = typer.Option("config.yaml", "--config", "-c", help="Config file path"),
    output_dir: Optional[str] = typer.Option(None, "--output", "-o", help="Output directory"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """
    Search for papers across multiple sources and generate bibliography.
    """
    setup_logging(verbose)
    
    console.print("\n[bold cyan]═══ REVIEW BUDDY - SEARCH PAPERS ═══[/bold cyan]\n")
    
    # Load config
    cfg = load_config(config_file)
    
    # Override with CLI args
    if query:
        cfg.search.query = query
    if year_from:
        cfg.search.year_from = year_from
    if max_results:
        cfg.search.max_results_per_source = max_results
    if output_dir:
        cfg.io.output_dir = output_dir
    
    if not cfg.search.query:
        console.print("[bold red]ERROR:[/bold red] No query specified!")
        console.print("Use --query or set query in config.yaml")
        raise typer.Exit(1)
    
    # Create output directory
    output_path = Path(cfg.io.output_dir)
    output_path.mkdir(exist_ok=True)
    
    # Create searcher
    config = Config(max_results_per_source=cfg.search.max_results_per_source)
    
    # Check available sources
    available = []
    if config.has_scopus_access():
        available.append("Scopus")
    if config.has_pubmed_access():
        available.append("PubMed")
    if config.has_arxiv_access():
        available.append("arXiv")
    if config.has_scholar_access():
        available.append("Google Scholar")
    if config.has_ieee_access():
        available.append("IEEE Xplore")
    
    if not available:
        console.print("[bold red]ERROR:[/bold red] No API keys configured!")
        console.print("Please create .env file with API keys (see README.md)")
        raise typer.Exit(1)
    
    console.print(f"[green]✓[/green] Available sources: {', '.join(available)}")
    console.print(f"[cyan]Query:[/cyan] {cfg.search.query}")
    console.print(f"[cyan]Year from:[/cyan] {cfg.search.year_from}")
    console.print()
    
    # Search
    searcher = PaperSearcher(config)
    papers = searcher.search_all(query=cfg.search.query, year_from=cfg.search.year_from)
    
    console.print(f"\n[bold green]✓ Found {len(papers)} unique papers[/bold green]\n")
    
    # Save results
    bib_file = output_path / "references.bib"
    ris_file = output_path / "references.ris"
    csv_file = output_path / "papers.csv"
    
    searcher.generate_bibliography(papers, format="bibtex", output_file=str(bib_file))
    searcher.generate_bibliography(papers, format="ris", output_file=str(ris_file))
    searcher.export_to_csv(papers, output_file=str(csv_file))
    
    console.print(f"[green]✓[/green] Saved: {bib_file}")
    console.print(f"[green]✓[/green] Saved: {ris_file}")
    console.print(f"[green]✓[/green] Saved: {csv_file}")
    console.print("\n[bold]Next step:[/bold] Run 'reviewbuddy filter' to filter papers")


@app.command()
def filter(
    engine: Optional[str] = typer.Option(None, "--engine", "-e", help="Filter engine: normal or ai"),
    config_file: str = typer.Option("config.yaml", "--config", "-c", help="Config file path"),
    input_file: Optional[str] = typer.Option(None, "--input", "-i", help="Input bibliography file"),
    output_dir: Optional[str] = typer.Option(None, "--output", "-o", help="Output directory"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """
    Filter papers using normal (keyword) or AI (LLM) engine.
    """
    setup_logging(verbose)
    
    console.print("\n[bold cyan]═══ REVIEW BUDDY - FILTER PAPERS ═══[/bold cyan]\n")
    
    # Load config
    cfg = load_config(config_file)
    
    # Override with CLI args
    if engine:
        cfg.engine = engine
    if input_file:
        cfg.io.input_path = input_file
    if output_dir:
        cfg.io.output_dir = output_dir
    
    console.print(f"[cyan]Filter engine:[/cyan] {cfg.engine}")
    console.print(f"[cyan]Input:[/cyan] {cfg.io.input_path}")
    console.print()
    
    # Load papers
    try:
        papers = load_papers(cfg.io.input_path)
        console.print(f"[green]✓[/green] Loaded {len(papers)} papers\n")
    except FileNotFoundError:
        console.print(f"[bold red]ERROR:[/bold red] Input file not found: {cfg.io.input_path}")
        console.print("Run 'reviewbuddy search' first to generate papers.")
        raise typer.Exit(1)
    
    # Get filter engine
    filter_config = cfg.get_filter_config()
    engine_obj = get_filter_engine(cfg.engine, filter_config)
    
    console.print(f"[cyan]Applying {cfg.engine} filters...[/cyan]\n")
    
    # Filter papers
    results = engine_obj.filter_records(papers)
    
    # Display summary
    summary = results['summary']
    console.print(f"\n[bold green]═══ FILTERING COMPLETE ═══[/bold green]")
    console.print(f"Initial papers:      {summary['initial_count']}")
    console.print(f"Papers kept:         {summary['final_count']}")
    console.print(f"Papers filtered:     {summary['total_filtered']}")
    
    if 'manual_review_count' in summary:
        console.print(f"Manual review:       {summary['manual_review_count']}")
    
    retention = summary['final_count'] / summary['initial_count'] * 100 if summary['initial_count'] > 0 else 0
    console.print(f"Retention rate:      {retention:.1f}%\n")
    
    # Postprocess and save
    output_files = postprocess_results(results, cfg.io.output_dir)
    
    console.print("[green]✓[/green] Output saved:")
    for key, path in output_files.items():
        console.print(f"  - {path}")
    
    # Save summary report
    report_path = Path(cfg.io.output_dir) / "filter_summary.txt"
    generate_summary_report(results, str(report_path))
    console.print(f"  - {report_path}")
    
    console.print("\n[bold]Next step:[/bold] Run 'reviewbuddy download' to download PDFs")


@app.command()
def download(
    config_file: str = typer.Option("config.yaml", "--config", "-c", help="Config file path"),
    input_file: Optional[str] = typer.Option(None, "--input", "-i", help="Input bibliography file"),
    output_dir: Optional[str] = typer.Option(None, "--output", "-o", help="Output PDF directory"),
    use_scihub: Optional[bool] = typer.Option(None, "--scihub/--no-scihub", help="Enable Sci-Hub"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """
    Download PDFs for papers in bibliography.
    """
    setup_logging(verbose)
    
    console.print("\n[bold cyan]═══ REVIEW BUDDY - DOWNLOAD PAPERS ═══[/bold cyan]\n")
    
    # Load config
    cfg = load_config(config_file)
    
    # Override with CLI args
    if input_file:
        cfg.io.input_path = input_file
    if output_dir:
        cfg.io.pdf_dir = output_dir
    if use_scihub is not None:
        cfg.download.use_scihub = use_scihub
    
    # Auto-select filtered or original file
    filtered_bib = Path(cfg.io.output_dir) / "references_filtered.bib"
    default_bib = Path(cfg.io.input_path)
    
    bib_file = filtered_bib if filtered_bib.exists() else default_bib
    
    if not bib_file.exists():
        console.print(f"[bold red]ERROR:[/bold red] No bibliography file found")
        console.print("Run 'reviewbuddy search' first")
        raise typer.Exit(1)
    
    console.print(f"[cyan]Input:[/cyan] {bib_file}")
    console.print(f"[cyan]Output:[/cyan] {cfg.io.pdf_dir}")
    console.print(f"[cyan]Sci-Hub:[/cyan] {'Enabled' if cfg.download.use_scihub else 'Disabled'}")
    console.print()
    
    # Create output directory
    Path(cfg.io.pdf_dir).mkdir(parents=True, exist_ok=True)
    
    # Download
    downloader = PaperDownloader(
        output_dir=cfg.io.pdf_dir,
        use_scihub=cfg.download.use_scihub,
        unpaywall_email=cfg.download.unpaywall_email
    )
    
    downloader.download_from_bib(str(bib_file))
    
    # Count PDFs
    pdf_count = len([f for f in Path(cfg.io.pdf_dir).iterdir() if f.suffix == ".pdf"])
    
    console.print(f"\n[bold green]✓ Downloaded {pdf_count} PDFs[/bold green]")
    console.print(f"Location: {cfg.io.pdf_dir}")
    console.print(f"Log: {Path(cfg.io.pdf_dir) / 'download.log'}")


@app.command()
def run(
    config_file: str = typer.Option("config.yaml", "--config", "-c", help="Config file path"),
    engine: Optional[str] = typer.Option(None, "--engine", "-e", help="Filter engine: normal or ai"),
    skip_search: bool = typer.Option(False, "--skip-search", help="Skip search step"),
    skip_filter: bool = typer.Option(False, "--skip-filter", help="Skip filter step"),
    skip_download: bool = typer.Option(False, "--skip-download", help="Skip download step"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """
    Run the full pipeline: search → filter → download.
    """
    setup_logging(verbose)
    
    console.print("\n[bold cyan]═══ REVIEW BUDDY - FULL PIPELINE ═══[/bold cyan]\n")
    
    # Load config to pass to subcommands
    cfg = load_config(config_file)
    if engine:
        cfg.engine = engine
    
    try:
        # Step 1: Search
        if not skip_search:
            console.print("[bold yellow]STEP 1: SEARCHING...[/bold yellow]")
            search(
                query=None,
                year_from=None,
                max_results=None,
                config_file=config_file,
                output_dir=None,
                verbose=verbose
            )
            console.print()
        
        # Step 2: Filter
        if not skip_filter:
            console.print("[bold yellow]STEP 2: FILTERING...[/bold yellow]")
            filter(
                engine=engine,
                config_file=config_file,
                input_file=None,
                output_dir=None,
                verbose=verbose
            )
            console.print()
        
        # Step 3: Download
        if not skip_download:
            console.print("[bold yellow]STEP 3: DOWNLOADING...[/bold yellow]")
            download(
                config_file=config_file,
                input_file=None,
                output_dir=None,
                use_scihub=None,
                verbose=verbose
            )
        
        console.print("\n[bold green]═══ PIPELINE COMPLETE! ═══[/bold green]")
        
    except typer.Exit as e:
        if e.exit_code != 0:
            console.print("\n[bold red]Pipeline failed![/bold red]")
            raise


@app.command()
def info(
    config_file: str = typer.Option("config.yaml", "--config", "-c", help="Config file path"),
):
    """
    Display current configuration.
    """
    console.print("\n[bold cyan]═══ CONFIGURATION INFO ═══[/bold cyan]\n")
    
    try:
        cfg = load_config(config_file)
        
        console.print(f"[cyan]Config file:[/cyan] {config_file}")
        console.print(f"[cyan]Filter engine:[/cyan] {cfg.engine}")
        console.print(f"\n[bold]I/O Settings:[/bold]")
        console.print(f"  Input:  {cfg.io.input_path}")
        console.print(f"  Output: {cfg.io.output_dir}")
        console.print(f"  PDFs:   {cfg.io.pdf_dir}")
        
        console.print(f"\n[bold]Search Settings:[/bold]")
        console.print(f"  Query:      {cfg.search.query[:60]}...")
        console.print(f"  Year from:  {cfg.search.year_from}")
        console.print(f"  Max results: {cfg.search.max_results_per_source}")
        
        if cfg.engine == "normal":
            console.print(f"\n[bold]Normal Filter:[/bold]")
            console.print(f"  Enabled filters: {', '.join(cfg.normal.enabled_filters)}")
            console.print(f"  Custom keywords: {len(cfg.normal.keywords)} filter(s)")
        else:
            console.print(f"\n[bold]AI Filter:[/bold]")
            console.print(f"  Model:      {cfg.ai.model}")
            console.print(f"  URL:        {cfg.ai.ollama_url}")
            console.print(f"  Threshold:  {cfg.ai.confidence_threshold}")
            console.print(f"  Filters:    {len(cfg.ai.filters)} defined")
        
        console.print(f"\n[bold]Download Settings:[/bold]")
        console.print(f"  Sci-Hub:   {'Enabled' if cfg.download.use_scihub else 'Disabled'}")
        console.print(f"  Email:     {cfg.download.unpaywall_email or 'Not set'}")
        console.print()
        
    except Exception as e:
        console.print(f"[bold red]ERROR:[/bold red] {e}")
        raise typer.Exit(1)


def main():
    """Main entry point"""
    app()


if __name__ == "__main__":
    main()
