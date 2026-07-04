"""Live terminal display for real-time VoIP stream analysis."""

import time
from datetime import datetime
from typing import List

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from voip_analyzer.live_analyzer import LiveStreamInfo


class LiveDisplay:
    """Terminal UI for displaying live VoIP stream metrics."""
    
    def __init__(self, console: Console = None):
        """
        Initialize live display.
        
        Args:
            console: Rich console instance (creates new if None)
        """
        self.console = console or Console()
        self.start_time = time.time()
    
    def create_header(self, stats: dict) -> Panel:
        """
        Create header panel with overall statistics.
        
        Args:
            stats: Statistics dictionary from LiveStreamAnalyzer
            
        Returns:
            Rich Panel with header information
        """
        uptime = int(time.time() - self.start_time)
        uptime_str = f"{uptime // 60}m {uptime % 60}s"
        
        header_text = Text()
        header_text.append("VoIP Live Analyzer", style="bold cyan")
        header_text.append(f" • Uptime: {uptime_str}", style="dim")
        header_text.append(f" • Packets: {stats.get('rtp_packets', 0)}", style="green")
        header_text.append(f" • Active: {stats.get('active_streams', 0)}", style="yellow")
        header_text.append(f" • Completed: {stats.get('completed_streams', 0)}", style="blue")
        
        return Panel(header_text, style="bold white", border_style="cyan")
    
    def create_streams_table(self, streams: List[LiveStreamInfo], title: str = "Active Streams") -> Table:
        """
        Create table displaying stream information.
        
        Args:
            streams: List of LiveStreamInfo objects
            title: Table title
            
        Returns:
            Rich Table with stream data
        """
        table = Table(title=title, show_header=True, header_style="bold magenta")
        
        table.add_column("Flow", style="cyan", no_wrap=True)
        table.add_column("Codec", style="green")
        table.add_column("Duration", justify="right")
        table.add_column("Packets", justify="right")
        table.add_column("Loss", justify="right")
        table.add_column("Jitter", justify="right")
        table.add_column("MOS", justify="right")
        table.add_column("Quality", style="bold")
        
        if not streams:
            table.add_row("No streams", "-", "-", "-", "-", "-", "-", "-")
            return table
        
        for stream in streams:
            # Format flow (truncate IPs if too long)
            flow = self._format_flow(stream.flow_id())
            
            # Format codec
            codec = stream.codec_name if stream.codec_name != "Unknown" else f"PT{stream.codec_pt}"
            
            # Format duration
            duration = f"{stream.duration():.1f}s"
            
            # Format packets
            packets = str(stream.packet_count)
            
            # Format packet loss with color coding
            loss_str = f"{stream.packet_loss_pct:.2f}%"
            if stream.packets_lost > 0:
                loss_str += f" ({stream.packets_lost})"
            loss_style = self._get_loss_style(stream.packet_loss_pct)
            
            # Format jitter with color coding
            jitter_str = f"{stream.avg_jitter_ms:.1f}ms"
            if stream.max_jitter_ms > 0:
                jitter_str += f" (max:{stream.max_jitter_ms:.1f})"
            jitter_style = self._get_jitter_style(stream.avg_jitter_ms)
            
            # Format MOS score with color coding
            mos_str = f"{stream.mos_score:.2f}" if stream.mos_score > 0 else "N/A"
            mos_style = self._get_mos_style(stream.mos_score)
            
            # Get quality indicator
            quality = self._get_quality_indicator(stream.mos_score)
            
            table.add_row(
                flow,
                codec,
                duration,
                packets,
                Text(loss_str, style=loss_style),
                Text(jitter_str, style=jitter_style),
                Text(mos_str, style=mos_style),
                quality,
            )
        
        return table
    
    def create_layout(self, active_streams: List[LiveStreamInfo], 
                     completed_streams: List[LiveStreamInfo],
                     stats: dict) -> Layout:
        """
        Create complete layout with header and tables.
        
        Args:
            active_streams: List of active streams
            completed_streams: List of completed streams
            stats: Statistics dictionary
            
        Returns:
            Rich Layout
        """
        layout = Layout()
        
        # Split into header and body
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
        )
        
        # Add header
        layout["header"].update(self.create_header(stats))
        
        # Create body layout
        if completed_streams:
            # Show both active and completed
            layout["body"].split_column(
                Layout(name="active"),
                Layout(name="completed", size=min(len(completed_streams) + 4, 15)),
            )
            layout["active"].update(self.create_streams_table(active_streams, "Active Streams"))
            layout["completed"].update(
                self.create_streams_table(completed_streams[-10:], "Recently Completed (last 10)")
            )
        else:
            # Only active streams
            layout["body"].update(self.create_streams_table(active_streams, "Active Streams"))
        
        return layout
    
    def _format_flow(self, flow: str) -> str:
        """Format flow ID, truncating IPs if needed."""
        # Truncate long IPs for display
        parts = flow.split("→")
        if len(parts) == 2:
            src = parts[0].split(":")
            dst = parts[1].split(":")
            if len(src) == 2 and len(dst) == 2:
                # Truncate IP if IPv6 or very long
                src_ip = src[0] if len(src[0]) < 20 else src[0][:17] + "..."
                dst_ip = dst[0] if len(dst[0]) < 20 else dst[0][:17] + "..."
                return f"{src_ip}:{src[1]}→{dst_ip}:{dst[1]}"
        return flow
    
    def _get_loss_style(self, loss_pct: float) -> str:
        """Get color style for packet loss percentage."""
        if loss_pct == 0:
            return "green"
        elif loss_pct < 0.5:
            return "yellow"
        elif loss_pct < 2.0:
            return "orange1"
        else:
            return "red"
    
    def _get_jitter_style(self, jitter_ms: float) -> str:
        """Get color style for jitter value."""
        if jitter_ms < 5:
            return "green"
        elif jitter_ms < 20:
            return "yellow"
        elif jitter_ms < 50:
            return "orange1"
        else:
            return "red"
    
    def _get_mos_style(self, mos: float) -> str:
        """Get color style for MOS score."""
        if mos >= 4.3:
            return "green bold"
        elif mos >= 4.0:
            return "green"
        elif mos >= 3.6:
            return "yellow"
        elif mos >= 3.1:
            return "orange1"
        elif mos > 0:
            return "red"
        else:
            return "dim"
    
    def _get_quality_indicator(self, mos: float) -> Text:
        """Get quality indicator text with emoji/symbol."""
        if mos >= 4.3:
            return Text("✓ Excellent", style="green bold")
        elif mos >= 4.0:
            return Text("✓ Good", style="green")
        elif mos >= 3.6:
            return Text("○ Fair", style="yellow")
        elif mos >= 3.1:
            return Text("⚠ Poor", style="orange1")
        elif mos > 0:
            return Text("✗ Bad", style="red bold")
        else:
            return Text("- N/A", style="dim")
    
    def render(self, active_streams: List[LiveStreamInfo], 
               completed_streams: List[LiveStreamInfo],
               stats: dict) -> Layout:
        """
        Render complete display.
        
        Args:
            active_streams: List of active streams
            completed_streams: List of completed streams
            stats: Statistics dictionary
            
        Returns:
            Rich Layout ready to display
        """
        return self.create_layout(active_streams, completed_streams, stats)


def format_stream_summary(stream: LiveStreamInfo) -> str:
    """
    Format a single stream as a summary line.
    
    Args:
        stream: Stream to format
        
    Returns:
        Formatted string
    """
    quality = "N/A"
    if stream.mos_score >= 4.3:
        quality = "Excellent"
    elif stream.mos_score >= 4.0:
        quality = "Good"
    elif stream.mos_score >= 3.6:
        quality = "Fair"
    elif stream.mos_score >= 3.1:
        quality = "Poor"
    elif stream.mos_score > 0:
        quality = "Bad"
    
    return (
        f"{stream.flow_id()} | {stream.codec_name} | "
        f"Duration: {stream.duration():.1f}s | "
        f"Packets: {stream.packet_count} | "
        f"Loss: {stream.packet_loss_pct:.2f}% | "
        f"Jitter: {stream.avg_jitter_ms:.1f}ms | "
        f"MOS: {stream.mos_score:.2f} ({quality})"
    )
