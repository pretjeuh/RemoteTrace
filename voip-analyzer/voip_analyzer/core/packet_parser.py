"""Packet parser for reading PCAP files and extracting RTP streams."""

import logging
from pathlib import Path
from typing import Generator, List, Optional

from scapy.all import IP, IPv6, UDP, PcapReader, RTP, Packet

from voip_analyzer.models.rtp_packet import RTPPacket

logger = logging.getLogger(__name__)


class PacketParser:
    """Parse PCAP files and extract RTP packets."""

    # Port ranges considered for RTP heuristic detection
    RTP_PORT_RANGES = [
        (5004, 5005),      # Standard RTP ports
        (5060, 5061),      # SIP signalling (SIP/UDP may carry embedded RTP info)
        (10000, 65000),    # Full VoIP RTP range used in practice
    ]

    # Minimum packet size for a valid RTP packet
    MIN_RTP_PACKET_SIZE = 12

    def __init__(self, verbose: bool = False, port_hints=None):
        """Initialize the packet parser.

        Args:
            verbose: Enable debug logging.
            port_hints: Optional RtpPortHints registry of SDP-learned RTP ports,
                so dynamically negotiated media ports (which the static ranges
                may miss) are recognised. Defaults to the shared singleton.
        """
        self.verbose = verbose
        if port_hints is None:
            from voip_analyzer.core.rtp_port_hints import get_shared_hints
            port_hints = get_shared_hints()
        self.port_hints = port_hints
        if verbose:
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.WARNING)

    def parse_file(self, filepath: str) -> Generator[RTPPacket, None, None]:
        """
        Parse a PCAP file and yield RTP packets.

        Args:
            filepath: Path to the PCAP file (.pcap or .pcapng)

        Yields:
            RTPPacket objects for each valid RTP packet found
        """
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"File not found: {filepath}")

        logger.info(f"Opening PCAP file: {filepath}")
        packet_count = 0
        rtp_count = 0
        skipped_count = 0

        try:
            with PcapReader(str(filepath)) as pcap_reader:
                for packet_number, packet in enumerate(pcap_reader):
                    try:
                        packet_count += 1

                        rtp_packet = self._extract_rtp(packet, packet_number)
                        if rtp_packet:
                            rtp_count += 1
                            yield rtp_packet
                    except Exception as e:
                        skipped_count += 1
                        if self.verbose:
                            logger.debug(
                                f"Skipped packet {packet_number}: {str(e)}"
                            )
                        continue
        except Exception as e:
            logger.error(f"Error reading PCAP file: {str(e)}")
            raise

        logger.info(
            f"Parsed {packet_count} packets, extracted {rtp_count} RTP packets, "
            f"skipped {skipped_count} packets"
        )

    def parse_stream(self, stream=None) -> Generator[RTPPacket, None, None]:
        """
        Parse a PCAP stream (from stdin or file handle) and yield RTP packets.
        
        This method is designed for real-time processing where packets arrive
        continuously rather than from a static file.

        Args:
            stream: Input stream (file handle or stdin). If None, uses sys.stdin.buffer

        Yields:
            RTPPacket objects for each valid RTP packet found
        """
        import sys
        
        if stream is None:
            stream = sys.stdin.buffer
            logger.info("Reading PCAP stream from stdin")
        else:
            logger.info("Reading PCAP stream from provided handle")

        packet_count = 0
        rtp_count = 0
        skipped_count = 0

        try:
            # Always pass the file object directly — PcapReader("-") opens a
            # literal file named "-" on some scapy versions, not stdin.
            pcap_reader = PcapReader(stream)
                
            try:
                for packet_number, packet in enumerate(pcap_reader):
                    try:
                        packet_count += 1

                        rtp_packet = self._extract_rtp(packet, packet_number)
                        if rtp_packet:
                            rtp_count += 1
                            if self.verbose and rtp_count % 100 == 0:
                                logger.debug(f"Processed {rtp_count} RTP packets")
                            yield rtp_packet
                    except Exception as e:
                        skipped_count += 1
                        if self.verbose:
                            logger.debug(
                                f"Skipped packet {packet_number}: {str(e)}"
                            )
                        continue
            finally:
                # Clean up the reader
                if hasattr(pcap_reader, 'close'):
                    pcap_reader.close()
                    
        except KeyboardInterrupt:
            logger.info("Stream parsing interrupted by user")
        except Exception as e:
            logger.error(f"Error reading PCAP stream: {str(e)}")
            raise
        finally:
            logger.info(
                f"Stream closed: parsed {packet_count} packets, "
                f"extracted {rtp_count} RTP packets, skipped {skipped_count} packets"
            )

    def _extract_rtp(
        self, packet: Packet, packet_number: int
    ) -> Optional[RTPPacket]:
        """
        Extract RTP packet from a scapy packet object.

        Args:
            packet: Scapy packet object
            packet_number: Index of this packet in the capture

        Returns:
            RTPPacket object if valid RTP found, None otherwise
        """
        # Support both IPv4 and IPv6
        if packet.haslayer(IP):
            ip_layer = packet[IP]
        elif packet.haslayer(IPv6):
            ip_layer = packet[IPv6]
        else:
            return None

        if not packet.haslayer(UDP):
            return None

        udp_layer = packet[UDP]

        # Check for RTP layer
        if not packet.haslayer(RTP):
            return self._heuristic_rtp_detection(
                packet, ip_layer, udp_layer, packet_number
            )

        rtp_layer = packet[RTP]
        return self._parse_rtp_layer(
            packet, ip_layer, udp_layer, rtp_layer, packet_number
        )

    def _heuristic_rtp_detection(
        self, packet: Packet, ip_layer, udp_layer: UDP, packet_number: int
    ) -> Optional[RTPPacket]:
        """
        Attempt to detect RTP packets using heuristics when scapy doesn't recognize it.

        This helps catch RTP packets that might be on non-standard ports or
        with unusual configurations.

        Args:
            packet: Full scapy packet
            ip_layer: IP layer
            udp_layer: UDP layer
            packet_number: Index in capture

        Returns:
            RTPPacket if heuristic detection succeeds, None otherwise
        """
        # Only consider ports in known RTP ranges to avoid false positives (e.g. DNS on port 53)
        if not (self.is_likely_rtp_port(udp_layer.sport) or self.is_likely_rtp_port(udp_layer.dport)):
            return None

        # Get UDP payload
        if len(udp_layer.payload) < self.MIN_RTP_PACKET_SIZE:
            return None

        payload = bytes(udp_layer.payload)

        # Check RTP version (first 2 bits should be 10 for V=2)
        if (payload[0] & 0xC0) != 0x80:  # Binary 10
            return None

        try:
            # Parse first few bytes to validate RTP structure
            first_byte = payload[0]
            version = (first_byte >> 6) & 0x03
            if version != 2:
                return None

            # Extract payload type (bits 1-7 of second byte)
            payload_type = payload[1] & 0x7F

            # Extract sequence number (bytes 2-3)
            sequence_number = (payload[2] << 8) | payload[3]

            # Extract timestamp (bytes 4-7)
            rtp_timestamp = (
                (payload[4] << 24)
                | (payload[5] << 16)
                | (payload[6] << 8)
                | payload[7]
            )

            # Extract SSRC (bytes 8-11)
            ssrc = (
                (payload[8] << 24)
                | (payload[9] << 16)
                | (payload[10] << 8)
                | payload[11]
            )

            # Validate payload type is in valid range
            if not (0 <= payload_type <= 127):
                return None

            # Build RTP packet from heuristic parse
            padding = bool(first_byte & 0x20)
            extension = bool(first_byte & 0x10)
            csrc_count = first_byte & 0x0F
            marker = bool(payload[1] & 0x80)

            return RTPPacket(
                arrival_timestamp=float(packet.time),
                packet_number=packet_number,
                src_ip=ip_layer.src,
                dst_ip=ip_layer.dst,
                src_port=udp_layer.sport,
                dst_port=udp_layer.dport,
                version=version,
                padding=padding,
                extension=extension,
                csrc_count=csrc_count,
                marker=marker,
                payload_type=payload_type,
                sequence_number=sequence_number,
                rtp_timestamp=rtp_timestamp,
                ssrc=ssrc,
                payload_size=len(payload),
                payload_data=payload,
            )
        except (IndexError, ValueError) as e:
            if self.verbose:
                logger.debug(f"Heuristic detection failed: {str(e)}")
            return None

    def _parse_rtp_layer(
        self,
        packet: Packet,
        ip_layer,
        udp_layer: UDP,
        rtp_layer: RTP,
        packet_number: int,
    ) -> Optional[RTPPacket]:
        """
        Parse RTP layer detected by scapy.

        Args:
            packet: Full scapy packet
            ip_layer: IP layer
            udp_layer: UDP layer
            rtp_layer: RTP layer
            packet_number: Index in capture

        Returns:
            RTPPacket object
        """
        try:
            payload_data = bytes(rtp_layer.payload) if rtp_layer.payload else None

            return RTPPacket(
                arrival_timestamp=float(packet.time),
                packet_number=packet_number,
                src_ip=ip_layer.src,
                dst_ip=ip_layer.dst,
                src_port=udp_layer.sport,
                dst_port=udp_layer.dport,
                version=rtp_layer.version,
                padding=rtp_layer.padding,
                extension=rtp_layer.extension,
                csrc_count=rtp_layer.csrc_count,
                marker=rtp_layer.marker,
                payload_type=rtp_layer.payload_type,
                sequence_number=rtp_layer.sequence,
                rtp_timestamp=rtp_layer.timestamp,
                ssrc=rtp_layer.ssrc,
                payload_size=len(rtp_layer.payload),
                payload_data=payload_data,
            )
        except Exception as e:
            if self.verbose:
                logger.debug(f"RTP layer parsing failed: {str(e)}")
            return None

    def is_likely_rtp_port(self, port: int) -> bool:
        """Check if a port is in a typical RTP range or SDP-learned."""
        if self.port_hints.contains(port):
            return True
        for start, end in self.RTP_PORT_RANGES:
            if start <= port <= end:
                return True
        return False
