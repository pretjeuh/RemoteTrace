"""Flow identification and grouping for RTP streams."""

import logging
from collections import defaultdict
from typing import Dict, List

from voip_analyzer.models.rtp_packet import RTPPacket

logger = logging.getLogger(__name__)


class FlowIdentifier:
    """Identify and group RTP packets into flows."""

    def __init__(self):
        """Initialize the flow identifier."""
        self.flows: Dict[tuple, List[RTPPacket]] = defaultdict(list)

    def add_packet(self, packet: RTPPacket) -> None:
        """
        Add a packet to the appropriate flow.

        Args:
            packet: RTPPacket to add
        """
        flow_id = packet.flow_id()
        self.flows[flow_id].append(packet)

    def get_flows(self) -> Dict[tuple, List[RTPPacket]]:
        """
        Get all identified flows.

        Returns:
            Dictionary mapping flow_id (5-tuple) to list of RTPPackets
        """
        return dict(self.flows)

    def get_flows_by_ssrc(self) -> Dict[int, List[RTPPacket]]:
        """
        Get flows grouped by SSRC (Synchronization Source).

        Returns:
            Dictionary mapping SSRC to list of RTPPackets
        """
        ssrc_flows = defaultdict(list)
        for packets in self.flows.values():
            for packet in packets:
                ssrc_flows[packet.ssrc].append(packet)
        return dict(ssrc_flows)

    def get_bidirectional_pairs(self) -> List[tuple]:
        """
        Identify bidirectional pairs of flows.

        Matches forward and reverse flows based on 5-tuple reversal.

        Returns:
            List of (forward_flow_id, reverse_flow_id, forward_packets, reverse_packets)
        """
        pairs = []
        processed_flows = set()

        for flow_id, packets in self.flows.items():
            if flow_id in processed_flows:
                continue

            # Get reverse flow
            reverse_flow_id = (flow_id[2], flow_id[3], flow_id[0], flow_id[1], flow_id[4])

            if reverse_flow_id in self.flows:
                reverse_packets = self.flows[reverse_flow_id]
                pairs.append(
                    (flow_id, reverse_flow_id, packets, reverse_packets)
                )
                processed_flows.add(flow_id)
                processed_flows.add(reverse_flow_id)

        return pairs

    def get_flow_summary(self) -> Dict[str, int]:
        """
        Get summary statistics about flows.

        Returns:
            Dictionary with flow count and packet count
        """
        total_packets = sum(len(packets) for packets in self.flows.values())
        return {
            "flow_count": len(self.flows),
            "total_packets": total_packets,
            "ssrc_count": len(self.get_flows_by_ssrc()),
        }
