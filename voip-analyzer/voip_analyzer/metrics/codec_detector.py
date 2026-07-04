"""RTP codec detection and analysis."""

import logging
from typing import List, Optional

from voip_analyzer.models.rtp_packet import RTPPacket

logger = logging.getLogger(__name__)


class CodecDetector:
    """Detect codecs from RTP payload type."""

    # Standard RTP payload type to codec mappings (RFC 3551)
    CODEC_MAP = {
        # Static payload types (0-34)
        0: {"name": "G.711 μ-law (PCMU)", "clock_rate": 8000, "channels": 1},
        1: {"name": "Reserved (GSM-EFR)", "clock_rate": 8000, "channels": 1},
        2: {"name": "G.726-32", "clock_rate": 8000, "channels": 1},
        3: {"name": "GSM", "clock_rate": 8000, "channels": 1},
        4: {"name": "G.723.1", "clock_rate": 8000, "channels": 1},
        5: {"name": "DVI4", "clock_rate": 8000, "channels": 1},
        6: {"name": "DVI4", "clock_rate": 16000, "channels": 1},
        7: {"name": "LPC", "clock_rate": 8000, "channels": 1},
        8: {"name": "G.711 A-law (PCMA)", "clock_rate": 8000, "channels": 1},
        9: {"name": "G.722", "clock_rate": 8000, "channels": 1},
        10: {"name": "L16 (16-bit linear, stereo)", "clock_rate": 44100, "channels": 2},
        11: {"name": "L16 (16-bit linear, mono)", "clock_rate": 44100, "channels": 1},
        12: {"name": "QCELP", "clock_rate": 8000, "channels": 1},
        13: {"name": "CN (Comfort Noise)", "clock_rate": 8000, "channels": 1},
        14: {"name": "MPA (MPEG audio)", "clock_rate": 90000, "channels": 1},
        15: {"name": "G.728", "clock_rate": 8000, "channels": 1},
        16: {"name": "DVI4", "clock_rate": 11025, "channels": 1},
        17: {"name": "DVI4", "clock_rate": 22050, "channels": 1},
        18: {"name": "G.729", "clock_rate": 8000, "channels": 1},
        19: {"name": "Reserved (CelB)", "clock_rate": 8000, "channels": 1},
        25: {"name": "CelB", "clock_rate": 8000, "channels": 1},
        26: {"name": "JPEG", "clock_rate": 90000, "channels": 1},
        28: {"name": "nv", "clock_rate": 90000, "channels": 1},
        31: {"name": "H.261", "clock_rate": 90000, "channels": 1},
        32: {"name": "MPV (MPEG video)", "clock_rate": 90000, "channels": 1},
        33: {"name": "MP2T (MPEG-2 TS)", "clock_rate": 90000, "channels": 1},
        34: {"name": "H.263", "clock_rate": 90000, "channels": 1},
        # Dynamic payload types (96-127) require SDP or heuristics
        # Common dynamic types
        96: {"name": "OPUS (Dynamic)", "clock_rate": 48000, "channels": 2},
        97: {"name": "VP8 (Dynamic)", "clock_rate": 90000, "channels": 1},
        98: {"name": "H.264 (Dynamic)", "clock_rate": 90000, "channels": 1},
        111: {"name": "OPUS (Telecom)", "clock_rate": 48000, "channels": 1},
        120: {"name": "SILK-WB (Dynamic)", "clock_rate": 16000, "channels": 1},
    }

    # Common bitrates by codec (for reference)
    CODEC_BITRATES = {
        "G.711 μ-law (PCMU)": 64,
        "G.711 A-law (PCMA)": 64,
        "G.729": 8,
        "G.722": 64,
        "G.726-32": 32,
        "OPUS": (8, 128),  # Variable rate
        "Speex": (2, 44),  # Variable rate
    }

    @classmethod
    def detect_codec(
        cls, packets: List[RTPPacket]
    ) -> tuple:
        """
        Detect codec from RTP packets.

        Args:
            packets: List of RTPPacket objects from a stream

        Returns:
            Tuple of (codec_name, payload_type, clock_rate)
        """
        if not packets:
            return ("Unknown", -1, 8000)

        # Get payload type from first packet
        payload_type = packets[0].payload_type

        # Look up in codec map
        if payload_type in cls.CODEC_MAP:
            codec_info = cls.CODEC_MAP[payload_type]
            return (
                codec_info["name"],
                payload_type,
                codec_info["clock_rate"],
            )

        # Dynamic payload type - try heuristics
        if 96 <= payload_type <= 127:
            return cls._heuristic_codec_detection(packets, payload_type)

        # Unknown codec
        logger.warning(f"Unknown codec payload type: {payload_type}")
        return (f"Unknown (PT {payload_type})", payload_type, 8000)

    @classmethod
    def _heuristic_codec_detection(
        cls, packets: List[RTPPacket], payload_type: int
    ) -> tuple:
        """
        Attempt to detect codec from payload characteristics.

        Args:
            packets: List of RTPPacket objects
            payload_type: The dynamic payload type

        Returns:
            Tuple of (codec_name, payload_type, clock_rate)
        """
        if not packets:
            return (f"Unknown Dynamic (PT {payload_type})", payload_type, 8000)

        # Analyze payload sizes
        payload_sizes = [p.payload_size for p in packets if p.payload_size > 0]
        if payload_sizes:
            avg_size = sum(payload_sizes) / len(payload_sizes)

            # Common payload sizes:
            # Opus at 48kHz, 20ms: ~200 bytes (variable)
            # G.729 at 8kHz, 10ms: ~10 bytes
            # SILK at 16kHz: ~40-80 bytes
            if avg_size > 100:
                return ("OPUS (Dynamic, detected)", payload_type, 48000)
            elif 30 < avg_size < 80:
                return ("SILK (Dynamic, detected)", payload_type, 16000)
            elif avg_size < 20:
                return ("G.729 (Dynamic, detected)", payload_type, 8000)

        # Fallback to default for dynamic type
        return (
            f"Unknown Dynamic (PT {payload_type})",
            payload_type,
            8000,
        )

    @classmethod
    def get_codec_name(cls, payload_type: int) -> str:
        """
        Get codec name from payload type.

        Args:
            payload_type: RTP payload type

        Returns:
            Codec name string
        """
        if payload_type in cls.CODEC_MAP:
            return cls.CODEC_MAP[payload_type]["name"]
        return f"Unknown (PT {payload_type})"

    @classmethod
    def get_clock_rate(cls, payload_type: int, default: int = 8000) -> int:
        """
        Get codec clock rate from payload type.

        Args:
            payload_type: RTP payload type
            default: Default clock rate if not found

        Returns:
            Clock rate in Hz
        """
        if payload_type in cls.CODEC_MAP:
            return cls.CODEC_MAP[payload_type]["clock_rate"]
        return default

    @classmethod
    def validate_codec_consistency(cls, packets: List[RTPPacket]) -> bool:
        """
        Check if all packets in a stream use the same codec.

        Args:
            packets: List of RTPPacket objects

        Returns:
            True if all packets have the same payload type
        """
        if not packets:
            return False
        payload_types = set(p.payload_type for p in packets)
        return len(payload_types) == 1
