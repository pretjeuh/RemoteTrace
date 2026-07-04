"""Stream information data model."""

from dataclasses import dataclass, field
from typing import List, Optional

from voip_analyzer.models.rtp_packet import RTPPacket


@dataclass
class RTPStream:
    """Represents a complete RTP stream."""

    # Stream identification
    stream_id: str  # Human-readable identifier (e.g., "192.168.1.10:16384->192.168.1.20:16384")
    ssrc: int  # Synchronization source
    flow_id: tuple  # 5-tuple (src_ip, src_port, dst_ip, dst_port, protocol)

    # Packets
    packets: List[RTPPacket] = field(default_factory=list)

    # Codec information
    codec_name: str = "Unknown"
    codec_pt: int = -1
    clock_rate: int = 8000  # Default to 8000 Hz

    # Temporal data
    start_time: Optional[float] = None
    end_time: Optional[float] = None

    # Computed metrics (populated during analysis)
    packet_loss: Optional[dict] = None
    jitter: Optional[dict] = None
    mos_score: Optional[float] = None
    r_factor: Optional[float] = None

    def duration(self) -> float:
        """Get stream duration in seconds."""
        if self.start_time is None or self.end_time is None:
            return 0.0
        return self.end_time - self.start_time

    def packet_count(self) -> int:
        """Get number of packets in stream."""
        return len(self.packets)

    def __str__(self) -> str:
        """String representation of stream."""
        duration = self.duration()
        return (
            f"RTP Stream {self.stream_id} ({self.codec_name}) "
            f"{self.packet_count()} packets, {duration:.1f}s"
        )

    def get_quality_label(self) -> str:
        """Get human-readable quality label based on MOS score."""
        if self.mos_score is None:
            return "Unknown"
        if self.mos_score > 4.3:
            return "Excellent"
        elif self.mos_score >= 4.0:
            return "Good"
        elif self.mos_score >= 3.6:
            return "Fair"
        elif self.mos_score >= 3.1:
            return "Poor"
        else:
            return "Bad"
