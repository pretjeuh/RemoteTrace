"""Unit tests for metric calculations."""

import pytest
from voip_analyzer.models.rtp_packet import RTPPacket
from voip_analyzer.metrics.packet_loss import PacketLossAnalyzer
from voip_analyzer.metrics.jitter import JitterAnalyzer
from voip_analyzer.metrics.quality_scores import QualityScoreCalculator


@pytest.fixture
def create_rtp_packet():
    """Factory for creating RTP packets."""
    def _create(
        seq_num=0,
        timestamp=0,
        ssrc=1234,
        arrival_time=0.0,
        payload_type=0,
        packet_num=0,
    ):
        return RTPPacket(
            arrival_timestamp=arrival_time,
            packet_number=packet_num,
            src_ip="192.168.1.10",
            dst_ip="192.168.1.20",
            src_port=5000,
            dst_port=5000,
            version=2,
            padding=False,
            extension=False,
            csrc_count=0,
            marker=False,
            payload_type=payload_type,
            sequence_number=seq_num,
            rtp_timestamp=timestamp,
            ssrc=ssrc,
            payload_size=160,
        )
    return _create


class TestPacketLoss:
    """Test packet loss detection."""

    def test_no_loss(self, create_rtp_packet):
        """Test detection with no packet loss."""
        packets = [
            create_rtp_packet(seq_num=i, timestamp=i*160, arrival_time=i*0.02)
            for i in range(10)
        ]
        result = PacketLossAnalyzer.analyze(packets)

        assert result["expected"] == 10
        assert result["received"] == 10
        assert result["lost"] == 0
        assert result["loss_percentage"] == 0.0

    def test_single_loss(self, create_rtp_packet):
        """Test detection with single packet loss."""
        packets = [
            create_rtp_packet(seq_num=i, timestamp=i*160, arrival_time=i*0.02)
            for i in [0, 1, 3, 4, 5]  # Packet 2 is lost
        ]
        result = PacketLossAnalyzer.analyze(packets)

        assert result["expected"] == 6
        assert result["received"] == 5
        assert result["lost"] == 1
        assert result["loss_percentage"] == pytest.approx(16.67, rel=0.01)

    def test_wraparound(self, create_rtp_packet):
        """Test detection with sequence number wraparound."""
        packets = [
            create_rtp_packet(seq_num=65534, timestamp=0, arrival_time=0.0),
            create_rtp_packet(seq_num=65535, timestamp=160, arrival_time=0.02),
            create_rtp_packet(seq_num=0, timestamp=320, arrival_time=0.04),
            create_rtp_packet(seq_num=1, timestamp=480, arrival_time=0.06),
        ]
        result = PacketLossAnalyzer.analyze(packets)

        assert result["expected"] == 4
        assert result["lost"] == 0

    def test_wraparound_with_loss(self, create_rtp_packet):
        """A gap straddling the wrap boundary is counted, not the wrap itself."""
        # 65535, [0 missing], 1, 2 -> one packet lost, span of 4.
        packets = [
            create_rtp_packet(seq_num=65535, timestamp=0, arrival_time=0.0),
            create_rtp_packet(seq_num=1, timestamp=320, arrival_time=0.04),
            create_rtp_packet(seq_num=2, timestamp=480, arrival_time=0.06),
        ]
        result = PacketLossAnalyzer.analyze(packets)

        assert result["expected"] == 4
        assert result["lost"] == 1

    def test_result_exposes_lost_key(self, create_rtp_packet):
        """The result dict uses ``lost`` (callers rely on this exact key)."""
        packets = [
            create_rtp_packet(seq_num=i, timestamp=i * 160, arrival_time=i * 0.02)
            for i in range(3)
        ]
        result = PacketLossAnalyzer.analyze(packets)

        # Guards against the live-path regression where "packets_lost" was read.
        assert "lost" in result
        assert "packets_lost" not in result


class TestJitter:
    """Test jitter calculation."""

    def test_no_jitter(self, create_rtp_packet):
        """Test with constant inter-arrival time (no jitter)."""
        packets = [
            create_rtp_packet(
                seq_num=i,
                timestamp=i*160,
                arrival_time=i*0.02,  # Constant 20ms intervals
                packet_num=i,
            )
            for i in range(10)
        ]
        result = JitterAnalyzer.analyze(packets, clock_rate=8000)

        # With constant timing, jitter should be very low
        assert result["avg_ms"] >= 0
        assert result["max_ms"] >= 0
        assert result["min_ms"] >= 0
        assert result["sample_count"] == len(packets) - 1

    def test_jitter_samples(self, create_rtp_packet):
        """Test that jitter samples are collected."""
        packets = [
            create_rtp_packet(seq_num=i, timestamp=i*160, arrival_time=i*0.02)
            for i in range(5)
        ]
        result = JitterAnalyzer.analyze(packets, clock_rate=8000)

        assert len(result["samples"]) == 4  # n-1 samples for n packets
        assert all(isinstance(s, float) for s in result["samples"])


class TestQualityScores:
    """Test quality score calculations."""

    def test_perfect_call(self):
        """Test MOS calculation for perfect call."""
        mos = QualityScoreCalculator.calculate_mos_simplified(
            packet_loss_percentage=0.0,
            jitter_ms=0.0,
            codec_name="G.711 μ-law (PCMU)",
        )
        # Perfect call should have high MOS
        assert mos > 4.3

    def test_poor_quality(self):
        """Test MOS calculation for poor quality call."""
        mos = QualityScoreCalculator.calculate_mos_simplified(
            packet_loss_percentage=10.0,
            jitter_ms=50.0,
            codec_name="G.711 μ-law (PCMU)",
        )
        # Poor quality should have lower MOS
        assert mos < 3.5

    def test_mos_bounds(self):
        """Test that MOS stays within bounds."""
        for loss in [0, 10, 50, 100]:
            for jitter in [0, 10, 100]:
                mos = QualityScoreCalculator.calculate_mos_simplified(loss, jitter)
                assert 1.0 <= mos <= 5.0

    def test_r_factor(self):
        """Test R-factor calculation."""
        r = QualityScoreCalculator.calculate_r_factor(
            packet_loss_percentage=0.0,
            jitter_ms=10.0,
        )
        assert 0 <= r <= 100

    def test_r_to_mos_conversion(self):
        """Test R-factor to MOS conversion."""
        # Perfect R-factor should give high MOS
        mos_perfect = QualityScoreCalculator.r_factor_to_mos(95)
        assert mos_perfect > 4.0

        # Poor R-factor should give low MOS
        mos_poor = QualityScoreCalculator.r_factor_to_mos(50)
        assert mos_poor < 3.5


class TestQualityCategories:
    """Test quality category assignments."""

    def test_quality_categories_mos(self):
        """Test MOS-based quality categories."""
        assert QualityScoreCalculator.get_quality_category(4.5) == "Excellent"
        assert QualityScoreCalculator.get_quality_category(4.2) == "Good"
        assert QualityScoreCalculator.get_quality_category(3.8) == "Fair"
        assert QualityScoreCalculator.get_quality_category(3.3) == "Poor"
        assert QualityScoreCalculator.get_quality_category(2.5) == "Bad"

    def test_quality_categories_r_factor(self):
        """Test R-factor-based quality categories."""
        assert QualityScoreCalculator.get_r_factor_category(95) == "Excellent"
        assert QualityScoreCalculator.get_r_factor_category(85) == "Good"
        assert QualityScoreCalculator.get_r_factor_category(75) == "Acceptable"
        assert QualityScoreCalculator.get_r_factor_category(65) == "Poor"
        assert QualityScoreCalculator.get_r_factor_category(50) == "Unacceptable"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
