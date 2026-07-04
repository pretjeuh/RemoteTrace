"""Output formatting for VoIP analyzer results."""

from typing import List

from rich.console import Console
from rich.table import Table

from voip_analyzer.models.stream_info import RTPStream

console = Console()


def print_header(title: str, filename: str) -> None:
    """Print a formatted header for the report."""
    console.print()
    console.print(f"[bold cyan]{'─' * 60}[/bold cyan]")
    console.print(f"[bold cyan]{title:^60}[/bold cyan]")
    console.print(f"[bold cyan]File: {filename:^50}[/bold cyan]")
    console.print(f"[bold cyan]{'─' * 60}[/bold cyan]")
    console.print()


def print_stream_summary(streams: List[RTPStream]) -> None:
    """Print a summary table of RTP streams."""
    if not streams:
        console.print("[yellow]No RTP streams found[/yellow]")
        return

    console.print(f"[bold]RTP Streams Found: {len(streams)}[/bold]\n")

    for i, stream in enumerate(streams, 1):
        console.print(f"[bold]Stream {i}: {stream.stream_id}[/bold]")

        # Create metrics table
        table = Table(title=None, show_header=True, header_style="bold")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        # Basic info
        table.add_row("Codec", stream.codec_name)
        table.add_row("Duration", f"{stream.duration():.2f} seconds")
        table.add_row("Packets", str(stream.packet_count()))

        # Metrics if available
        if stream.packet_loss:
            loss_pct = stream.packet_loss.get("loss_percentage", 0)
            status = "[green]✓[/green]" if loss_pct == 0 else "[yellow]⚠[/yellow]"
            table.add_row(
                "Packet Loss",
                f"{stream.packet_loss.get('lost', 0)} packets "
                f"({loss_pct:.2f}%) {status}",
            )

        if stream.jitter:
            jitter_avg = stream.jitter.get("avg_ms", 0)
            status = "[green]✓[/green]" if jitter_avg < 30 else "[yellow]⚠[/yellow]"
            table.add_row(
                "Jitter",
                f"Avg: {jitter_avg:.2f}ms, "
                f"Max: {stream.jitter.get('max_ms', 0):.2f}ms {status}",
            )

        if stream.mos_score is not None:
            mos = stream.mos_score
            quality = stream.get_quality_label()

            # Color code by quality
            if mos > 4.3:
                color = "green"
                symbol = "✓"
            elif mos >= 4.0:
                color = "green"
                symbol = "✓"
            elif mos >= 3.6:
                color = "yellow"
                symbol = "⚠"
            else:
                color = "red"
                symbol = "✗"

            table.add_row(
                "MOS Score",
                f"[{color}]{mos:.2f} ({quality}) {symbol}[/{color}]",
            )

        if stream.r_factor is not None:
            table.add_row("R-Factor", f"{stream.r_factor:.2f}")

        console.print(table)
        console.print()


def print_stream_details(stream: RTPStream) -> None:
    """Print detailed information about a stream."""
    console.print(f"[bold]Stream Details: {stream.stream_id}[/bold]")
    console.print(f"SSRC: {stream.ssrc}")
    console.print(f"Codec: {stream.codec_name} (PT {stream.codec_pt})")
    console.print(f"Clock Rate: {stream.clock_rate} Hz")
    console.print(f"Start Time: {stream.start_time}")
    console.print(f"End Time: {stream.end_time}")
    console.print(f"Duration: {stream.duration():.3f} seconds")
    console.print(f"Packet Count: {stream.packet_count()}")

    if stream.packet_loss:
        console.print("\n[bold cyan]Packet Loss Analysis[/bold cyan]")
        loss_info = stream.packet_loss
        console.print(f"Expected: {loss_info.get('expected', 0)} packets")
        console.print(f"Received: {loss_info.get('received', 0)} packets")
        console.print(f"Lost: {loss_info.get('lost', 0)} packets")
        console.print(f"Loss Percentage: {loss_info.get('loss_percentage', 0):.2f}%")

    if stream.jitter:
        console.print("\n[bold cyan]Jitter Analysis[/bold cyan]")
        jitter_info = stream.jitter
        console.print(f"Average: {jitter_info.get('avg_ms', 0):.3f} ms")
        console.print(f"Maximum: {jitter_info.get('max_ms', 0):.3f} ms")
        console.print(f"Minimum: {jitter_info.get('min_ms', 0):.3f} ms")

    if stream.mos_score is not None:
        console.print("\n[bold cyan]Quality Metrics[/bold cyan]")
        console.print(f"MOS Score: {stream.mos_score:.2f}")
        console.print(f"Quality: {stream.get_quality_label()}")
        if stream.r_factor is not None:
            console.print(f"R-Factor: {stream.r_factor:.2f}")
    console.print()


def print_comparison_summary(pbx_streams: List[RTPStream], endpoint_streams: List[RTPStream]) -> None:
    """Print a comparison between PBX and endpoint captures."""
    console.print()
    console.print("[bold cyan]" + "─" * 70 + "[/bold cyan]")
    console.print("[bold cyan]Side-by-Side Comparison: PBX vs Endpoint[/bold cyan]")
    console.print("[bold cyan]" + "─" * 70 + "[/bold cyan]")
    console.print()

    # Calculate averages
    def avg_metric(streams: List[RTPStream], metric: str, subkey: str = None) -> float:
        """Calculate average of a metric across streams."""
        values = []
        for stream in streams:
            if metric == "loss":
                if stream.packet_loss and "loss_percentage" in stream.packet_loss:
                    values.append(stream.packet_loss["loss_percentage"])
            elif metric == "jitter":
                if stream.jitter and "avg_ms" in stream.jitter:
                    values.append(stream.jitter["avg_ms"])
            elif metric == "mos":
                if stream.mos_score is not None:
                    values.append(stream.mos_score)
        return sum(values) / len(values) if values else 0

    table = Table(show_header=True, header_style="bold")
    table.add_column("Metric", style="cyan")
    table.add_column("PBX Capture", style="magenta")
    table.add_column("Endpoint Capture", style="yellow")

    pbx_loss = avg_metric(pbx_streams, "loss")
    endpoint_loss = avg_metric(endpoint_streams, "loss")
    table.add_row("Avg Packet Loss (%)", f"{pbx_loss:.2f}%", f"{endpoint_loss:.2f}%")

    pbx_jitter = avg_metric(pbx_streams, "jitter")
    endpoint_jitter = avg_metric(endpoint_streams, "jitter")
    table.add_row("Avg Jitter (ms)", f"{pbx_jitter:.2f}", f"{endpoint_jitter:.2f}")

    pbx_mos = avg_metric(pbx_streams, "mos")
    endpoint_mos = avg_metric(endpoint_streams, "mos")
    table.add_row("Avg MOS Score", f"{pbx_mos:.2f}", f"{endpoint_mos:.2f}")

    console.print(table)
    console.print()

    # Analysis
    console.print("[bold]Analysis:[/bold]")
    if endpoint_loss > pbx_loss:
        loss_delta = endpoint_loss - pbx_loss
        console.print(
            f"  [yellow]⚠[/yellow] Endpoint shows higher packet loss (+{loss_delta:.2f}%)"
        )
    if endpoint_jitter > pbx_jitter:
        jitter_delta = endpoint_jitter - pbx_jitter
        console.print(
            f"  [yellow]⚠[/yellow] Endpoint shows higher jitter (+{jitter_delta:.2f}ms)"
        )
    if endpoint_mos < pbx_mos:
        mos_delta = pbx_mos - endpoint_mos
        console.print(
            f"  [yellow]⚠[/yellow] Endpoint shows lower MOS score (-{mos_delta:.2f})"
        )

    if pbx_loss == 0 and endpoint_loss == 0 and abs(pbx_jitter - endpoint_jitter) < 1:
        console.print("  [green]✓[/green] Both captures show similar quality")

    console.print()


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"[bold red]✗ Error: {message}[/bold red]")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[bold yellow]⚠ Warning: {message}[/bold yellow]")


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"[bold green]✓ {message}[/bold green]")


def print_no_streams_found() -> None:
    """Print message when no streams are found."""
    console.print("[yellow]⚠ No RTP streams found in this file[/yellow]")
