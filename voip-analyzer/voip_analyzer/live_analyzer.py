"""Real-time VoIP stream analyzer for live packet captures."""

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from voip_analyzer.metrics.codec_detector import CodecDetector
from voip_analyzer.metrics.jitter import JitterAnalyzer
from voip_analyzer.metrics.packet_loss import PacketLossAnalyzer
from voip_analyzer.metrics.quality_scores import QualityScoreCalculator
from voip_analyzer.models.rtp_packet import RTPPacket

logger = logging.getLogger(__name__)


@dataclass
class LiveStreamInfo:
    """Information about a live RTP stream."""
    
    ssrc: int
    src_ip: str
    src_port: int
    dst_ip: str
    dst_port: int
    
    # Stream metadata
    start_time: float = 0.0
    last_packet_time: float = 0.0
    packet_count: int = 0
    
    # Codec info
    codec_name: str = "Unknown"
    codec_pt: int = 0
    clock_rate: int = 8000
    
    # Metrics
    packet_loss_pct: float = 0.0
    packets_lost: int = 0
    avg_jitter_ms: float = 0.0
    max_jitter_ms: float = 0.0
    mos_score: float = 0.0
    r_factor: float = 0.0
    
    # Rolling window of packets (limited size)
    packets: List[RTPPacket] = field(default_factory=list)
    
    def flow_id(self) -> str:
        """Generate flow identifier."""
        return f"{self.src_ip}:{self.src_port}→{self.dst_ip}:{self.dst_port}"
    
    def duration(self) -> float:
        """Calculate stream duration in seconds."""
        if self.start_time == 0:
            return 0.0
        return self.last_packet_time - self.start_time
    
    def is_active(self, current_time: float, timeout: float = 30.0) -> bool:
        """Check if stream is still active (received packet recently)."""
        if self.last_packet_time == 0:
            return True
        return (current_time - self.last_packet_time) < timeout


class LiveStreamAnalyzer:
    """Analyze RTP streams in real-time as packets arrive."""
    
    def __init__(self, window_seconds: int = 60, stream_timeout: int = 30):
        """
        Initialize live stream analyzer.
        
        Args:
            window_seconds: Rolling window size in seconds for keeping packets
            stream_timeout: Seconds of inactivity before considering stream ended
        """
        self.window_seconds = window_seconds
        self.stream_timeout = stream_timeout
        
        # Track streams by SSRC
        self.streams: Dict[int, LiveStreamInfo] = {}
        
        # Track completed streams
        self.completed_streams: List[LiveStreamInfo] = []
        
        # Statistics
        self.total_packets_processed = 0
        self.total_rtp_packets = 0
        
        logger.info(
            f"LiveStreamAnalyzer initialized: window={window_seconds}s, "
            f"timeout={stream_timeout}s"
        )
    
    def add_packet(self, packet: RTPPacket) -> None:
        """
        Add a packet to the analyzer and update metrics.
        
        Args:
            packet: RTP packet to process
        """
        self.total_packets_processed += 1
        
        ssrc = packet.ssrc
        current_time = packet.arrival_timestamp
        
        # Get or create stream
        if ssrc not in self.streams:
            stream = LiveStreamInfo(
                ssrc=ssrc,
                src_ip=packet.src_ip,
                src_port=packet.src_port,
                dst_ip=packet.dst_ip,
                dst_port=packet.dst_port,
                start_time=current_time,
                last_packet_time=current_time,
            )
            self.streams[ssrc] = stream
            logger.debug(f"New stream detected: SSRC={ssrc}, flow={stream.flow_id()}")
        else:
            stream = self.streams[ssrc]
        
        # Add packet to stream
        stream.packets.append(packet)
        stream.packet_count += 1
        stream.last_packet_time = current_time
        self.total_rtp_packets += 1
        
        # Maintain rolling window - remove old packets
        self._trim_window(stream, current_time)
        
        # Update metrics periodically (every 10 packets or so)
        if stream.packet_count % 10 == 0 or stream.packet_count < 20:
            self._update_stream_metrics(stream)
    
    def _trim_window(self, stream: LiveStreamInfo, current_time: float) -> None:
        """
        Remove packets outside the rolling window.
        
        Args:
            stream: Stream to trim
            current_time: Current timestamp
        """
        cutoff_time = current_time - self.window_seconds
        
        # Keep only packets within window
        original_count = len(stream.packets)
        stream.packets = [
            p for p in stream.packets 
            if p.arrival_timestamp >= cutoff_time
        ]
        
        removed = original_count - len(stream.packets)
        if removed > 0 and logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Trimmed {removed} packets from stream SSRC={stream.ssrc}")
    
    def _update_stream_metrics(self, stream: LiveStreamInfo) -> None:
        """
        Calculate and update metrics for a stream.
        
        Args:
            stream: Stream to update
        """
        if len(stream.packets) < 2:
            return
        
        # Sort packets by arrival time
        sorted_packets = sorted(stream.packets, key=lambda p: p.arrival_timestamp)
        
        # Detect codec (use most recent packets for accuracy)
        if stream.codec_name == "Unknown" or stream.packet_count % 50 == 0:
            codec_name, pt, clock_rate = CodecDetector.detect_codec(sorted_packets[-20:])
            stream.codec_name = codec_name
            stream.codec_pt = pt
            stream.clock_rate = clock_rate
        
        # Calculate packet loss
        try:
            loss_metrics = PacketLossAnalyzer.analyze(sorted_packets)
            stream.packet_loss_pct = loss_metrics["loss_percentage"]
            stream.packets_lost = loss_metrics["packets_lost"]
        except Exception as e:
            logger.debug(f"Packet loss calculation error: {e}")
        
        # Calculate jitter
        try:
            jitter_metrics = JitterAnalyzer.analyze(sorted_packets, stream.clock_rate)
            stream.avg_jitter_ms = jitter_metrics["avg_ms"]
            stream.max_jitter_ms = jitter_metrics["max_ms"]
        except Exception as e:
            logger.debug(f"Jitter calculation error: {e}")
        
        # Calculate quality scores
        try:
            quality_metrics = QualityScoreCalculator.calculate_call_quality_metrics(
                packet_loss_percentage=stream.packet_loss_pct,
                jitter_ms=stream.avg_jitter_ms,
                codec_name=stream.codec_name,
                one_way_delay_ms=stream.avg_jitter_ms * 2.5,
            )
            stream.mos_score = quality_metrics["mos"]
            stream.r_factor = quality_metrics["r_factor"]
        except Exception as e:
            logger.debug(f"Quality score calculation error: {e}")
    
    def check_inactive_streams(self, current_time: float) -> List[LiveStreamInfo]:
        """
        Check for inactive streams and move them to completed.
        
        Args:
            current_time: Current timestamp
            
        Returns:
            List of newly completed streams
        """
        newly_completed = []
        inactive_ssrcs = []
        
        for ssrc, stream in self.streams.items():
            if not stream.is_active(current_time, self.stream_timeout):
                # Final metrics update
                self._update_stream_metrics(stream)
                
                logger.info(
                    f"Stream completed: SSRC={ssrc}, duration={stream.duration():.1f}s, "
                    f"packets={stream.packet_count}, MOS={stream.mos_score:.2f}"
                )
                
                newly_completed.append(stream)
                inactive_ssrcs.append(ssrc)
        
        # Move to completed
        for ssrc in inactive_ssrcs:
            stream = self.streams.pop(ssrc)
            self.completed_streams.append(stream)
        
        return newly_completed
    
    def get_active_streams(self) -> List[LiveStreamInfo]:
        """Get list of currently active streams."""
        return list(self.streams.values())
    
    def get_completed_streams(self) -> List[LiveStreamInfo]:
        """Get list of completed streams."""
        return self.completed_streams
    
    def get_all_streams(self) -> List[LiveStreamInfo]:
        """Get all streams (active + completed)."""
        return self.get_active_streams() + self.get_completed_streams()
    
    def get_statistics(self) -> Dict[str, int]:
        """Get analyzer statistics."""
        return {
            "total_packets": self.total_packets_processed,
            "rtp_packets": self.total_rtp_packets,
            "active_streams": len(self.streams),
            "completed_streams": len(self.completed_streams),
            "total_streams": len(self.streams) + len(self.completed_streams),
        }
