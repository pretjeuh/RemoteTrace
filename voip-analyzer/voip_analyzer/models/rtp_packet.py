"""RTP packet data model."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class RTPPacket:
    """Represents a single RTP packet extracted from a pcap file."""

    # Packet metadata
    arrival_timestamp: float  # Seconds since epoch
    packet_number: int  # Index in capture

    # IP/UDP layer
    src_ip: str
    dst_ip: str
    src_port: int
    dst_port: int

    # RTP header fields
    version: int  # Should be 2
    padding: bool
    extension: bool
    csrc_count: int
    marker: bool
    payload_type: int  # Codec identifier (0-127)
    sequence_number: int  # 16-bit sequence number
    rtp_timestamp: int  # 32-bit, codec-specific clock
    ssrc: int  # Synchronization source identifier

    # Payload
    payload_size: int
    payload_data: Optional[bytes] = None

    def is_valid_rtp(self) -> bool:
        """Validate that this is a valid RTP header."""
        return (
            self.version == 2
            and 0 <= self.payload_type <= 127
            and self.sequence_number >= 0
            and self.rtp_timestamp >= 0
            and self.ssrc >= 0
        )

    def flow_id(self) -> tuple:
        """Get the flow identifier (5-tuple)."""
        return (self.src_ip, self.src_port, self.dst_ip, self.dst_port, "UDP")

    def reverse_flow_id(self) -> tuple:
        """Get the reverse flow identifier."""
        return (self.dst_ip, self.dst_port, self.src_ip, self.src_port, "UDP")
