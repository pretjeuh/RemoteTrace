"""VoIP Analyzer CLI entry point."""

import logging
import sys
import threading
import time
from pathlib import Path

import click
from rich.console import Console
from rich.live import Live

from voip_analyzer.cli.output import (
    print_error,
    print_header,
    print_stream_summary,
    print_warning,
)
from voip_analyzer.cli.live_output import LiveDisplay, format_stream_summary
from voip_analyzer.core.flow_identifier import FlowIdentifier
from voip_analyzer.core.packet_parser import PacketParser
from voip_analyzer.core.rtp_stream import RTPStreamAnalyzer
from voip_analyzer.live_analyzer import LiveStreamAnalyzer
from voip_analyzer.metrics.codec_detector import CodecDetector
from voip_analyzer.metrics.packet_loss import PacketLossAnalyzer
from voip_analyzer.metrics.jitter import JitterAnalyzer
from voip_analyzer.metrics.quality_scores import QualityScoreCalculator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@click.group()
def cli():
    """VoIP Call Analyzer - Analyze RTP streams for quality metrics."""
    pass


@cli.command()
@click.argument("filepath", type=click.Path(exists=True))
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose output with debug information",
)
@click.option(
    "--output",
    "-o",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format",
)
def analyze(filepath: str, verbose: bool, output: str):
    """Analyze a PCAP file for RTP stream quality metrics."""
    try:
        filepath = Path(filepath)

        # Create parser and parse file
        parser = PacketParser(verbose=verbose)

        # Parse all packets
        click.echo("Parsing PCAP file...", err=True)
        all_packets = list(parser.parse_file(str(filepath)))

        if not all_packets:
            print_warning("No RTP packets found in file")
            return

        click.echo(f"Found {len(all_packets)} RTP packets", err=True)

        # Create stream analyzer and add packets
        click.echo("Analyzing RTP streams...", err=True)
        stream_analyzer = RTPStreamAnalyzer()
        for packet in all_packets:
            stream_analyzer.add_packet(packet)

        streams = stream_analyzer.get_streams()
        if not streams:
            print_warning("No complete RTP streams found")
            return

        click.echo(f"Identified {len(streams)} streams", err=True)

        # Detect codecs and calculate metrics
        click.echo("Calculating metrics...", err=True)
        for stream in streams:
            if stream.packets:
                # Detect codec
                codec_name, pt, clock_rate = CodecDetector.detect_codec(stream.packets)
                stream.codec_name = codec_name
                stream.codec_pt = pt
                stream.clock_rate = clock_rate

                # Sort packets by arrival time for metric calculations
                sorted_packets = sorted(stream.packets, key=lambda p: p.arrival_timestamp)

                # Calculate packet loss
                loss_metrics = PacketLossAnalyzer.analyze(sorted_packets)
                stream.packet_loss = loss_metrics

                # Calculate jitter
                jitter_metrics = JitterAnalyzer.analyze(sorted_packets, clock_rate)
                stream.jitter = jitter_metrics

                # Calculate quality scores
                quality_metrics = QualityScoreCalculator.calculate_call_quality_metrics(
                    packet_loss_percentage=loss_metrics["loss_percentage"],
                    jitter_ms=jitter_metrics["avg_ms"],
                    codec_name=codec_name,
                    one_way_delay_ms=jitter_metrics["avg_ms"] * 2.5,
                )
                stream.mos_score = quality_metrics["mos"]
                stream.r_factor = quality_metrics["r_factor"]

        # Print results
        print_header("VoIP Call Analysis Report", filepath.name)
        print_stream_summary(streams)

        if output == "json":
            click.echo("[INFO] JSON output not yet implemented", err=True)

    except FileNotFoundError as e:
        print_error(f"File not found: {e}")
        sys.exit(1)
    except Exception as e:
        print_error(f"Analysis failed: {e}")
        if verbose:
            logger.exception("Exception details:")
        sys.exit(1)


@cli.command()
@click.argument("filepath1", type=click.Path(exists=True))
@click.argument("filepath2", type=click.Path(exists=True))
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose output with debug information",
)
def compare(filepath1: str, filepath2: str, verbose: bool):
    """Compare RTP stream quality metrics from two PCAP files."""
    try:
        filepath1 = Path(filepath1)
        filepath2 = Path(filepath2)

        # Parse first file
        click.echo(f"Analyzing {filepath1.name}...", err=True)
        parser = PacketParser(verbose=verbose)
        all_packets1 = list(parser.parse_file(str(filepath1)))

        # Parse second file
        click.echo(f"Analyzing {filepath2.name}...", err=True)
        all_packets2 = list(parser.parse_file(str(filepath2)))

        if not all_packets1 or not all_packets2:
            print_error("No RTP packets found in one or both files")
            sys.exit(1)

        # Create stream analyzers
        stream_analyzer1 = RTPStreamAnalyzer()
        for packet in all_packets1:
            stream_analyzer1.add_packet(packet)

        stream_analyzer2 = RTPStreamAnalyzer()
        for packet in all_packets2:
            stream_analyzer2.add_packet(packet)

        streams1 = stream_analyzer1.get_streams()
        streams2 = stream_analyzer2.get_streams()

        # Detect codecs and calculate metrics
        click.echo("Calculating metrics...", err=True)
        for stream in streams1 + streams2:
            if stream.packets:
                # Detect codec
                codec_name, pt, clock_rate = CodecDetector.detect_codec(stream.packets)
                stream.codec_name = codec_name
                stream.codec_pt = pt
                stream.clock_rate = clock_rate

                # Sort packets by arrival time for metric calculations
                sorted_packets = sorted(stream.packets, key=lambda p: p.arrival_timestamp)

                # Calculate packet loss
                loss_metrics = PacketLossAnalyzer.analyze(sorted_packets)
                stream.packet_loss = loss_metrics

                # Calculate jitter
                jitter_metrics = JitterAnalyzer.analyze(sorted_packets, clock_rate)
                stream.jitter = jitter_metrics

                # Calculate quality scores
                quality_metrics = QualityScoreCalculator.calculate_call_quality_metrics(
                    packet_loss_percentage=loss_metrics["loss_percentage"],
                    jitter_ms=jitter_metrics["avg_ms"],
                    codec_name=codec_name,
                    one_way_delay_ms=jitter_metrics["avg_ms"] * 2.5,
                )
                stream.mos_score = quality_metrics["mos"]
                stream.r_factor = quality_metrics["r_factor"]

        # Print results
        print_header(f"Comparison Report", "")
        click.echo(f"\n[cyan]File 1: {filepath1.name}[/cyan]")
        print_stream_summary(streams1)

        click.echo(f"\n[cyan]File 2: {filepath2.name}[/cyan]")
        print_stream_summary(streams2)

    except FileNotFoundError as e:
        print_error(f"File not found: {e}")
        sys.exit(1)
    except Exception as e:
        print_error(f"Comparison failed: {e}")
        if verbose:
            logger.exception("Exception details:")
        sys.exit(1)


@cli.command()
@click.argument("filepath", type=click.Path(exists=True))
def validate(filepath: str):
    """Validate PCAP file for RTP streams."""
    try:
        filepath = Path(filepath)
        parser = PacketParser(verbose=False)
        packets = list(parser.parse_file(str(filepath)))

        click.echo(f"Total packets parsed: {len(packets)}")

        if packets:
            # Basic validation
            unique_ssrcs = len(set(p.ssrc for p in packets))
            unique_pts = len(set(p.payload_type for p in packets))
            unique_flows = len(set(p.flow_id() for p in packets))

            click.echo(f"Unique SSRCs: {unique_ssrcs}")
            click.echo(f"Unique payload types: {unique_pts}")
            click.echo(f"Unique flows: {unique_flows}")
            click.echo("[green]✓ File appears valid[/green]")
        else:
            click.echo("[yellow]⚠ No RTP packets found[/yellow]")

    except Exception as e:
        print_error(f"Validation failed: {e}")
        sys.exit(1)


@cli.command()
@click.option(
    "--update-interval",
    "-u",
    type=float,
    default=2.0,
    help="Display update interval in seconds (default: 2.0)",
)
@click.option(
    "--window",
    "-w",
    type=int,
    default=60,
    help="Rolling window size in seconds for metrics (default: 60)",
)
@click.option(
    "--stream-timeout",
    "-t",
    type=int,
    default=30,
    help="Stream inactivity timeout in seconds (default: 30)",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose logging",
)
def live(update_interval: float, window: int, stream_timeout: int, verbose: bool):
    """Analyze RTP streams in real-time from stdin (live packet capture).
    
    This command reads PCAP data from stdin and displays live metrics.
    Designed to work with tcpdump or RemoteTrace tool.
    
    Example:
        tcpdump -i en0 -U -s 0 -w - 'udp' | python -m voip_analyzer live
    """
    try:
        # Set up logging
        if verbose:
            logging.basicConfig(
                level=logging.DEBUG,
                format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            )
            click.echo("[DEBUG] Verbose logging enabled", err=True)
        else:
            # Suppress most logging for clean display
            logging.basicConfig(level=logging.WARNING)
        
        click.echo("Starting live VoIP analyzer...", err=True)
        click.echo(f"Settings: update={update_interval}s, window={window}s, timeout={stream_timeout}s", err=True)
        click.echo("Reading from stdin... (Press Ctrl+C to stop)\n", err=True)
        
        # Create parser and analyzer
        parser = PacketParser(verbose=verbose)
        analyzer = LiveStreamAnalyzer(
            window_seconds=window,
            stream_timeout=stream_timeout,
        )
        
        # Create display
        console = Console()
        display = LiveDisplay(console=console)
        
        # Track last update time
        last_update = time.time()
        last_check = time.time()
        
        # Start live display
        with Live(display.render([], [], {}), console=console, refresh_per_second=4) as live_display:
            try:
                # Read packets from stdin
                for packet in parser.parse_stream():
                    # Add packet to analyzer
                    analyzer.add_packet(packet)
                    
                    current_time = time.time()
                    
                    # Check for inactive streams periodically
                    if current_time - last_check >= 5.0:
                        completed = analyzer.check_inactive_streams(packet.arrival_timestamp)
                        if completed and verbose:
                            for stream in completed:
                                click.echo(f"Stream completed: {format_stream_summary(stream)}", err=True)
                        last_check = current_time
                    
                    # Update display at specified interval
                    if current_time - last_update >= update_interval:
                        active_streams = analyzer.get_active_streams()
                        completed_streams = analyzer.get_completed_streams()
                        stats = analyzer.get_statistics()
                        
                        live_display.update(
                            display.render(active_streams, completed_streams, stats)
                        )
                        last_update = current_time
                        
            except KeyboardInterrupt:
                click.echo("\n\nStopping live analyzer...", err=True)
        
        # Final summary
        click.echo("\n" + "="*60, err=True)
        click.echo("Live Analysis Summary", err=True)
        click.echo("="*60, err=True)
        
        stats = analyzer.get_statistics()
        click.echo(f"Total packets processed: {stats['total_packets']}", err=True)
        click.echo(f"RTP packets: {stats['rtp_packets']}", err=True)
        click.echo(f"Total streams detected: {stats['total_streams']}", err=True)
        click.echo(f"  - Active: {stats['active_streams']}", err=True)
        click.echo(f"  - Completed: {stats['completed_streams']}", err=True)
        
        # Show completed streams summary
        completed_streams = analyzer.get_completed_streams()
        if completed_streams:
            click.echo("\nCompleted Streams:", err=True)
            for stream in completed_streams:
                click.echo(f"  - {format_stream_summary(stream)}", err=True)
        
        # Show active streams (if any remaining)
        active_streams = analyzer.get_active_streams()
        if active_streams:
            click.echo("\nActive Streams (ongoing):", err=True)
            for stream in active_streams:
                click.echo(f"  - {format_stream_summary(stream)}", err=True)
        
    except Exception as e:
        print_error(f"Live analysis failed: {e}")
        if verbose:
            logger.exception("Exception details:")
        sys.exit(1)


@cli.command()
@click.option("--port", "-p", type=int, default=7654, show_default=True, help="Port for the web dashboard.")
@click.option("--host", default="127.0.0.1", show_default=True, help="Bind address.")
@click.option("--update-interval", "-u", type=float, default=2.0, show_default=True, help="Live update interval in seconds.")
@click.option("--window", "-w", type=int, default=60, show_default=True, help="Rolling window size in seconds.")
@click.option("--stream-timeout", "-t", type=int, default=30, show_default=True, help="Stream inactivity timeout in seconds.")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging.")
def web(port: int, host: str, update_interval: float, window: int, stream_timeout: int, verbose: bool) -> None:
    """Start the web dashboard and analyze live capture from stdin.

    Reads PCAP data from stdin (live tcpdump pipe) and serves a browser dashboard.
    Also accepts PCAP file uploads via the dashboard UI.

    Example:
        tcpdump -i eth0 -U -s 0 -w - 'udp' | python -m voip_analyzer web --port 7654
    """
    try:
        from voip_analyzer.web.app import app as flask_app, ingest_live_stream
    except ImportError:
        print_error("Flask is required for the web dashboard. Install it with: pip install flask")
        sys.exit(1)

    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING)
        logging.getLogger("werkzeug").setLevel(logging.WARNING)

    import os

    from voip_analyzer.core.rtp_port_hints import get_shared_hints
    from voip_analyzer.core.stream_tee import PcapTee
    from voip_analyzer.core.tshark_runner import tshark_available

    hints = get_shared_hints()
    parser = PacketParser(verbose=verbose, port_hints=hints)
    analyzer = LiveStreamAnalyzer(window_seconds=window, stream_timeout=stream_timeout)

    # Grab stdin now, before Flask touches the process stdio.
    src_fd = os.dup(sys.stdin.fileno())

    sip_enabled = tshark_available()
    if sip_enabled:
        # Fan the single pcap stream out to the RTP parser and the SIP dissector.
        tee = PcapTee(src_fd).start()
        rtp_stream = tee.rtp_reader

        from voip_analyzer.core.sip_analyzer import SipDialogAnalyzer
        from voip_analyzer.core.tshark_runner import TsharkSipSource
        from voip_analyzer.web.app import ingest_sip_stream, set_sip_analyzer

        sip_analyzer = SipDialogAnalyzer(port_hints=hints)
        set_sip_analyzer(sip_analyzer)
        sip_source = TsharkSipSource(tee.sip_reader)
        threading.Thread(
            target=ingest_sip_stream,
            args=(sip_analyzer, sip_source, analyzer),
            daemon=True,
        ).start()
    else:
        # No tshark: RTP-only, read stdin directly (unchanged legacy behaviour).
        click.echo(
            "[WARN] tshark not found — SIP call analysis disabled (RTP only). "
            "Install Wireshark or set VOIP_TSHARK_PATH to enable it.",
            err=True,
        )
        rtp_stream = os.fdopen(src_fd, "rb", buffering=0)

    ingest_thread = threading.Thread(
        target=ingest_live_stream,
        args=(analyzer, parser, update_interval, rtp_stream),
        daemon=True,
    )
    ingest_thread.start()

    click.echo(f"[INFO] VoIP Analyzer web dashboard → http://{host}:{port}", err=True)
    click.echo("[INFO] Reading live capture from stdin (Ctrl+C to stop)", err=True)

    flask_app.run(host=host, port=port, threaded=True, use_reloader=False)


if __name__ == "__main__":
    cli()
