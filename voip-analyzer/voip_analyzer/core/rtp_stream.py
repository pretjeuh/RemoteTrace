"""RTP stream identification and grouping."""

import logging
from collections import defaultdict
from typing import Dict, List

from voip_analyzer.models.rtp_packet import RTPPacket
from voip_analyzer.models.stream_info import RTPStream

logger = logging.getLogger(__name__)


class RTPStreamAnalyzer:
    """Identify and group RTP packets into streams."""

    def __init__(self):
        """Initialize the stream analyzer."""
        self.streams: Dict[str, RTPStream] = {}
        self.ssrc_to_stream: Dict[int, str] = {}

    def add_packet(self, packet: RTPPacket) -> None:
        """
        Add a packet to a stream, creating the stream if necessary.

        Args:
            packet: RTPPacket to add
        """
        # Create stream identifier from flow
        flow_id = packet.flow_id()
        stream_id = self._flow_to_stream_id(flow_id)

        # Get or create stream
        if stream_id not in self.streams:
            self.streams[stream_id] = RTPStream(
                stream_id=stream_id,
                ssrc=packet.ssrc,
                flow_id=flow_id,
            )
            self.ssrc_to_stream[packet.ssrc] = stream_id

        stream = self.streams[stream_id]
        stream.packets.append(packet)

        # Update temporal bounds
        if stream.start_time is None or packet.arrival_timestamp < stream.start_time:
            stream.start_time = packet.arrival_timestamp
        if stream.end_time is None or packet.arrival_timestamp > stream.end_time:
            stream.end_time = packet.arrival_timestamp

    def get_streams(self) -> List[RTPStream]:
        """
        Get all identified streams.

        Returns:
            List of RTPStream objects
        """
        return list(self.streams.values())

    def get_stream_by_ssrc(self, ssrc: int) -> RTPStream:
        """
        Get a stream by its SSRC.

        Args:
            ssrc: Synchronization source identifier

        Returns:
            RTPStream if found, None otherwise
        """
        if ssrc in self.ssrc_to_stream:
            stream_id = self.ssrc_to_stream[ssrc]
            return self.streams.get(stream_id)
        return None

    def sort_streams_by_duration(self) -> List[RTPStream]:
        """
        Get streams sorted by duration (longest first).

        Returns:
            List of RTPStream objects sorted by duration
        """
        return sorted(self.streams.values(), key=lambda s: s.duration(), reverse=True)

    def filter_by_codec_pt(self, payload_type: int) -> List[RTPStream]:
        """
        Filter streams by codec payload type.

        Args:
            payload_type: RTP payload type to filter by

        Returns:
            List of RTPStream objects with matching payload type
        """
        result = []
        for stream in self.streams.values():
            if stream.packets and stream.packets[0].payload_type == payload_type:
                result.append(stream)
        return result

    def validate_streams(self) -> Dict[str, any]:
        """
        Validate all streams for consistency.

        Returns:
            Dictionary with validation results
        """
        issues = []
        for stream in self.streams.values():
            if not stream.packets:
                issues.append(f"Stream {stream.stream_id}: No packets")
                continue

            # Check payload type consistency
            payload_types = set(p.payload_type for p in stream.packets)
            if len(payload_types) > 1:
                issues.append(
                    f"Stream {stream.stream_id}: "
                    f"Multiple payload types {payload_types}"
                )

            # Check SSRC consistency
            ssrcs = set(p.ssrc for p in stream.packets)
            if len(ssrcs) > 1:
                issues.append(
                    f"Stream {stream.stream_id}: "
                    f"Multiple SSRCs {ssrcs}"
                )

        return {
            "total_streams": len(self.streams),
            "valid_streams": len(self.streams) - len(issues),
            "issues": issues,
        }

    @staticmethod
    def _flow_to_stream_id(flow_id: tuple) -> str:
        """
        Convert a flow ID (5-tuple) to a human-readable stream ID.

        Args:
            flow_id: Tuple of (src_ip, src_port, dst_ip, dst_port, protocol)

        Returns:
            String representation like "192.168.1.10:5000->192.168.1.20:5000"
        """
        src_ip, src_port, dst_ip, dst_port, protocol = flow_id
        return f"{src_ip}:{src_port}->{dst_ip}:{dst_port}"
