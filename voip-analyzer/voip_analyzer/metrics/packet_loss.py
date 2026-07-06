"""Packet loss detection and analysis."""

import logging
from typing import List, Optional

from voip_analyzer.models.rtp_packet import RTPPacket

logger = logging.getLogger(__name__)


class PacketLossAnalyzer:
    """Analyze packet loss in RTP streams."""

    @staticmethod
    def analyze(packets: List[RTPPacket]) -> dict:
        """
        Analyze packet loss in a stream based on RTP sequence numbers.

        The RTP sequence number is a 16-bit field that increments by 1 for each
        packet. By analyzing the sequence numbers, we can detect missing packets.

        Args:
            packets: List of RTPPacket objects from a single stream

        Returns:
            Dictionary with packet loss analysis results:
            {
                'expected': total expected packets,
                'received': total received packets,
                'lost': number of lost packets,
                'duplicates': number of duplicate packets,
                'loss_percentage': percentage of packets lost,
                'loss_locations': list of loss event details,
                'reordered': number of reordered packets,
            }
        """
        if not packets:
            return {
                "expected": 0,
                "received": 0,
                "lost": 0,
                "duplicates": 0,
                "loss_percentage": 0.0,
                "loss_locations": [],
                "reordered": 0,
            }

        # Unwrap 16-bit sequence numbers into a monotonic space, walking packets
        # in the order supplied (callers pass arrival order). Sorting by raw
        # sequence number breaks across a wraparound: for [65534, 65535, 0, 1]
        # a numeric sort yields [0, 1, 65534, 65535], making the span look like
        # ~65536 instead of 4. Unwrapping preserves the true continuity.
        unwrapped = PacketLossAnalyzer._unwrap_sequences(packets)

        # Expected count = span from the lowest to highest unwrapped seq.
        expected = (max(unwrapped) - min(unwrapped)) + 1

        # Count received unique packets
        seq_numbers = [p.sequence_number for p in packets]
        unique_seq_count = len(set(seq_numbers))
        received = len(packets)

        # Detect duplicates
        duplicates = received - unique_seq_count

        # Calculate lost packets
        lost = expected - unique_seq_count

        # Calculate loss percentage
        loss_percentage = (lost / expected * 100) if expected > 0 else 0

        # Find loss locations, ordering by unwrapped sequence so the wrap point
        # isn't misread as a huge gap.
        seq_ordered = [
            p for _, p in sorted(zip(unwrapped, packets), key=lambda t: t[0])
        ]
        loss_locations = PacketLossAnalyzer._identify_loss_locations(seq_ordered)

        # Detect reordered packets
        reordered = PacketLossAnalyzer._count_reordered(packets)

        return {
            "expected": expected,
            "received": received,
            "lost": lost,
            "duplicates": duplicates,
            "loss_percentage": loss_percentage,
            "loss_locations": loss_locations,
            "reordered": reordered,
        }

    @staticmethod
    def _unwrap_sequences(packets: List[RTPPacket]) -> List[int]:
        """Map 16-bit RTP sequence numbers to a continuous (non-wrapping) space.

        Walks packets in supplied order, accumulating a signed per-step delta
        (via :meth:`_seq_diff`) onto a running base. A forward wrap (65535 -> 0)
        yields a small positive delta rather than a -65535 jump, so the returned
        values stay monotonic through the wrap boundary.

        Args:
            packets: Packets in arrival order.

        Returns:
            One unwrapped sequence value per packet, index-aligned to ``packets``.
        """
        unwrapped: List[int] = []
        running = 0
        prev: Optional[int] = None
        for packet in packets:
            seq = packet.sequence_number
            if prev is None:
                running = seq
            else:
                running += PacketLossAnalyzer._seq_diff(seq, prev)
            unwrapped.append(running)
            prev = seq
        return unwrapped

    @staticmethod
    def _seq_diff(a: int, b: int) -> int:
        """
        Calculate sequence number difference accounting for 16-bit wraparound.

        Args:
            a: First sequence number
            b: Second sequence number (typically earlier)

        Returns:
            Difference accounting for wraparound at 65535
        """
        diff = (a - b) % 65536
        # If diff > 32768, it's likely a wraparound backwards (shouldn't happen in normal case)
        if diff > 32768:
            diff -= 65536
        return diff

    @staticmethod
    def _identify_loss_locations(sorted_packets: List[RTPPacket]) -> List[dict]:
        """
        Identify specific locations where packet loss occurred.

        Args:
            sorted_packets: Packets sorted by sequence number

        Returns:
            List of loss event dictionaries with details
        """
        loss_locations = []

        for i in range(1, len(sorted_packets)):
            prev_seq = sorted_packets[i - 1].sequence_number
            curr_seq = sorted_packets[i].sequence_number

            gap = PacketLossAnalyzer._seq_diff(curr_seq, prev_seq)

            if gap > 1:  # Gap detected
                loss_locations.append(
                    {
                        "after_seq": prev_seq,
                        "before_seq": curr_seq,
                        "gap_size": gap - 1,
                        "after_time": sorted_packets[i - 1].arrival_timestamp,
                        "before_time": sorted_packets[i].arrival_timestamp,
                    }
                )

        return loss_locations

    @staticmethod
    def _count_reordered(packets: List[RTPPacket]) -> int:
        """
        Count packets that arrived out of order.

        A packet is considered reordered if it arrived after a packet with
        a higher sequence number.

        Args:
            packets: List of RTPPacket objects in arrival order

        Returns:
            Number of reordered packets
        """
        reordered_count = 0
        max_seq_seen = -1

        for packet in packets:
            if packet.sequence_number < max_seq_seen:
                reordered_count += 1
            max_seq_seen = max(max_seq_seen, packet.sequence_number)

        return reordered_count

    @staticmethod
    def get_quality_assessment(loss_percentage: float) -> tuple:
        """
        Get quality assessment based on packet loss percentage.

        Args:
            loss_percentage: Percentage of packets lost

        Returns:
            Tuple of (quality_label, severity)
        """
        if loss_percentage == 0:
            return ("No packet loss", "good")
        elif loss_percentage < 0.5:
            return ("Very low packet loss", "good")
        elif loss_percentage < 1.0:
            return ("Low packet loss", "acceptable")
        elif loss_percentage < 2.0:
            return ("Moderate packet loss", "warning")
        elif loss_percentage < 5.0:
            return ("High packet loss", "poor")
        else:
            return ("Very high packet loss", "bad")
