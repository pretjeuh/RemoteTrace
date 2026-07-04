"""Jitter calculation according to RFC 3550."""

import logging
import math
from typing import List

from voip_analyzer.models.rtp_packet import RTPPacket

logger = logging.getLogger(__name__)


class JitterAnalyzer:
    """Calculate jitter metrics for RTP streams."""

    @staticmethod
    def analyze(packets: List[RTPPacket], clock_rate: int = 8000) -> dict:
        """
        Calculate jitter metrics using RFC 3550 definition.

        RFC 3550 defines jitter as:
        D(i,j) = (R_j - R_i) - (S_j - S_i)
        J(i) = J(i-1) + (|D(i-1,i)| - J(i-1)) / 16

        Where:
        - R_i = arrival time of packet i (receiver clock, seconds)
        - S_i = RTP timestamp of packet i (sender clock, normalized to seconds)
        - D(i,j) = transit time difference
        - J(i) = jitter estimate (smoothing factor 1/16)

        Args:
            packets: List of RTPPacket objects from a single stream
            clock_rate: Codec clock rate in Hz (8000 for G.711, 48000 for Opus)

        Returns:
            Dictionary with jitter statistics:
            {
                'avg_ms': average jitter in milliseconds,
                'max_ms': maximum jitter observed,
                'min_ms': minimum jitter observed,
                'samples': list of jitter samples,
                'sample_count': total number of jitter measurements,
            }
        """
        if len(packets) < 2:
            return {
                "avg_ms": 0.0,
                "max_ms": 0.0,
                "min_ms": 0.0,
                "samples": [],
                "sample_count": 0,
            }

        # Sort packets by arrival time
        sorted_packets = sorted(packets, key=lambda p: p.arrival_timestamp)

        # Validate clock rate
        if clock_rate <= 0:
            logger.warning(f"Invalid clock rate {clock_rate}, using default 8000")
            clock_rate = 8000

        jitter = 0.0  # Cumulative jitter estimate
        transit_prev = None
        jitter_samples = []

        for i in range(len(sorted_packets)):
            packet = sorted_packets[i]

            # Arrival time in seconds (from pcap timestamp)
            arrival_time = packet.arrival_timestamp

            # RTP timestamp normalized to seconds
            # RTP timestamp uses codec-specific clock rate
            rtp_timestamp_sec = packet.rtp_timestamp / float(clock_rate)

            # Transit time = arrival_time - rtp_timestamp_sec
            # This represents the one-way delay from sender to receiver
            transit = arrival_time - rtp_timestamp_sec

            if transit_prev is not None:
                # Transit time difference between consecutive packets
                # D = (R_j - R_i) - (S_j - S_i)
                d = transit - transit_prev

                # RFC 3550 jitter formula
                # J = J + (|D| - J) / 16
                jitter = jitter + (abs(d) - jitter) / 16.0

                # Store jitter sample in milliseconds
                jitter_ms = jitter * 1000.0
                jitter_samples.append(jitter_ms)

            transit_prev = transit

        # Calculate statistics
        if jitter_samples:
            avg_jitter = sum(jitter_samples) / len(jitter_samples)
            max_jitter = max(jitter_samples)
            min_jitter = min(jitter_samples)
        else:
            avg_jitter = 0.0
            max_jitter = 0.0
            min_jitter = 0.0

        return {
            "avg_ms": avg_jitter,
            "max_ms": max_jitter,
            "min_ms": min_jitter,
            "samples": jitter_samples,
            "sample_count": len(jitter_samples),
        }

    @staticmethod
    def analyze_arrival_intervals(packets: List[RTPPacket]) -> dict:
        """
        Analyze inter-arrival time intervals (alternative jitter measure).

        This calculates the variation in time between consecutive packet arrivals,
        which is different from RFC 3550 jitter but provides useful information.

        Args:
            packets: List of RTPPacket objects from a single stream

        Returns:
            Dictionary with interval statistics:
            {
                'mean_interval_ms': mean inter-arrival interval,
                'stdev_interval_ms': standard deviation,
                'min_interval_ms': minimum interval,
                'max_interval_ms': maximum interval,
            }
        """
        if len(packets) < 2:
            return {
                "mean_interval_ms": 0.0,
                "stdev_interval_ms": 0.0,
                "min_interval_ms": 0.0,
                "max_interval_ms": 0.0,
            }

        # Sort by arrival time
        sorted_packets = sorted(packets, key=lambda p: p.arrival_timestamp)

        # Calculate intervals between consecutive packets
        intervals = []
        for i in range(1, len(sorted_packets)):
            interval = (
                sorted_packets[i].arrival_timestamp
                - sorted_packets[i - 1].arrival_timestamp
            ) * 1000.0  # Convert to milliseconds

            if interval >= 0:  # Only count positive intervals
                intervals.append(interval)

        if not intervals:
            return {
                "mean_interval_ms": 0.0,
                "stdev_interval_ms": 0.0,
                "min_interval_ms": 0.0,
                "max_interval_ms": 0.0,
            }

        # Calculate statistics
        mean_interval = sum(intervals) / len(intervals)

        # Standard deviation
        variance = sum((x - mean_interval) ** 2 for x in intervals) / len(intervals)
        stdev_interval = math.sqrt(variance)

        return {
            "mean_interval_ms": mean_interval,
            "stdev_interval_ms": stdev_interval,
            "min_interval_ms": min(intervals),
            "max_interval_ms": max(intervals),
        }

    @staticmethod
    def get_quality_assessment(jitter_ms: float) -> tuple:
        """
        Get quality assessment based on jitter.

        ITU-T G.131 recommends:
        - < 20ms: Good
        - 20-50ms: Acceptable
        - > 50ms: Problematic

        Args:
            jitter_ms: Average jitter in milliseconds

        Returns:
            Tuple of (quality_label, severity)
        """
        if jitter_ms < 5:
            return ("Excellent jitter", "good")
        elif jitter_ms < 20:
            return ("Good jitter", "good")
        elif jitter_ms < 30:
            return ("Acceptable jitter", "acceptable")
        elif jitter_ms < 50:
            return ("Poor jitter", "warning")
        else:
            return ("Very poor jitter", "bad")
