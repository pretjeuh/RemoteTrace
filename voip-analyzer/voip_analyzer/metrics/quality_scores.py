"""Quality score calculation - MOS and R-factor."""

import logging
import math
from typing import Optional

logger = logging.getLogger(__name__)


class QualityScoreCalculator:
    """Calculate MOS (Mean Opinion Score) and R-factor."""

    # Base MOS values for different codecs
    CODEC_BASE_MOS = {
        "G.711 μ-law (PCMU)": 4.4,
        "G.711 A-law (PCMA)": 4.4,
        "G.722": 4.1,
        "G.729": 3.9,
        "OPUS": 4.3,
        "Speex": 3.8,
        "iLBC": 3.9,
        "AMR": 3.7,
        "GSM": 3.5,
    }

    # Codec equipment impairment factors (Ie) for ITU E-Model
    CODEC_IMPAIRMENT = {
        "G.711 μ-law (PCMU)": 0,
        "G.711 A-law (PCMA)": 0,
        "G.722": 1,
        "G.729": 11,
        "OPUS": 6,
        "Speex": 10,
        "iLBC": 9,
        "AMR": 13,
        "GSM": 20,
    }

    # Codec robustness factors (Bpl) - higher = more robust to packet loss
    CODEC_ROBUSTNESS = {
        "G.711 μ-law (PCMU)": 20,
        "G.711 A-law (PCMA)": 20,
        "G.722": 25,
        "G.729": 35,
        "OPUS": 30,
        "Speex": 32,
        "iLBC": 38,
        "AMR": 40,
        "GSM": 50,
    }

    @staticmethod
    def calculate_mos_simplified(
        packet_loss_percentage: float,
        jitter_ms: float,
        codec_name: str = "G.711 μ-law (PCMU)",
    ) -> float:
        """
        Calculate MOS (Mean Opinion Score) using simplified E-Model approach.

        This is a simplified calculation suitable for quick assessment.
        MOS ranges from 1.0 (bad) to 5.0 (excellent).

        Algorithm:
        1. Start with codec base MOS
        2. Apply packet loss degradation: -0.3 * sqrt(loss_pct)
        3. Apply jitter degradation: -0.1 * sqrt(jitter_ms / 10)
        4. Clamp result to 1.0 - 5.0

        Args:
            packet_loss_percentage: Percentage of packets lost (0-100)
            jitter_ms: Average jitter in milliseconds
            codec_name: Name of codec used

        Returns:
            MOS score (1.0 to 5.0)
        """
        # Get base MOS for codec, default to G.711
        base_mos = QualityScoreCalculator.CODEC_BASE_MOS.get(codec_name, 4.4)

        # Validate inputs
        packet_loss_percentage = max(0, min(100, packet_loss_percentage))
        jitter_ms = max(0, jitter_ms)

        # Calculate degradation from packet loss
        # More aggressive degradation as loss increases
        loss_impact = -0.3 * math.sqrt(packet_loss_percentage)

        # Calculate degradation from jitter
        # Normalized to 10ms baseline
        jitter_impact = -0.1 * math.sqrt(jitter_ms / 10.0)

        # Calculate MOS
        mos = base_mos + loss_impact + jitter_impact

        # Clamp to valid range [1.0, 5.0]
        mos = max(1.0, min(5.0, mos))

        return mos

    @staticmethod
    def calculate_r_factor(
        packet_loss_percentage: float,
        jitter_ms: float,
        one_way_delay_ms: float = 150,
        codec_name: str = "G.711 μ-law (PCMU)",
    ) -> float:
        """
        Calculate R-factor using ITU-T G.107 E-Model.

        The R-factor represents overall transmission quality from 0-100:
        - 90-100: Excellent
        - 80-89: Good
        - 70-79: Acceptable
        - 60-69: Poor
        - < 60: Unacceptable

        Algorithm (simplified):
        R = R0 - Is - Id - Ie_eff

        Where:
        - R0 = 93.2 (baseline for ideal connection)
        - Is = simultaneous impairment (0 for VoIP)
        - Id = delay impairment
        - Ie_eff = effective equipment impairment (codec + packet loss)

        Args:
            packet_loss_percentage: Percentage of packets lost (0-100)
            jitter_ms: Average jitter in milliseconds
            one_way_delay_ms: One-way transmission delay (default 150ms)
            codec_name: Name of codec used

        Returns:
            R-factor score (0-100)
        """
        # Base R value (ideal connection)
        R0 = 93.2

        # Simultaneous impairment (0 for modern VoIP)
        Is = 0

        # Delay impairment (ITU-T G.131)
        # Estimate one-way delay from jitter if not provided
        if one_way_delay_ms <= 0:
            one_way_delay_ms = jitter_ms * 2.5

        # Delay impairment formula
        if one_way_delay_ms < 177.3:
            Id = 0.024 * one_way_delay_ms
        else:
            Id = 0.024 * one_way_delay_ms + 0.11 * (one_way_delay_ms - 177.3)

        # Equipment impairment (codec + packet loss)
        Ie = QualityScoreCalculator.CODEC_IMPAIRMENT.get(codec_name, 0)
        Bpl = QualityScoreCalculator.CODEC_ROBUSTNESS.get(codec_name, 25)

        # Packet loss impairment
        # Ie_eff = Ie + (95 - Ie) * Ppl / (Ppl + Bpl)
        packet_loss_percentage = max(0, min(100, packet_loss_percentage))

        if packet_loss_percentage > 0:
            loss_impairment = (95 - Ie) * packet_loss_percentage / (
                packet_loss_percentage + Bpl
            )
        else:
            loss_impairment = 0

        Ie_eff = Ie + loss_impairment

        # Calculate R-factor
        R = R0 - Is - Id - Ie_eff

        # Clamp to valid range [0, 100]
        R = max(0, min(100, R))

        return R

    @staticmethod
    def r_factor_to_mos(r_factor: float) -> float:
        """
        Convert R-factor to MOS using ITU-T G.107 conversion formula.

        Formula:
        If R < 0: MOS = 1.0
        If R > 100: MOS = 4.5
        Else: MOS = 1 + 0.035*R + 0.000007*R*(R-60)*(100-R)

        Args:
            r_factor: R-factor value (0-100)

        Returns:
            MOS score (1.0-4.5)
        """
        if r_factor < 0:
            return 1.0
        elif r_factor > 100:
            return 4.5
        else:
            # Standard ITU conversion formula
            mos = 1.0 + 0.035 * r_factor + 0.000007 * r_factor * (r_factor - 60) * (100 - r_factor)
            # Clamp to valid range
            return max(1.0, min(4.5, mos))

    @staticmethod
    def get_quality_category(mos: float) -> str:
        """
        Get quality category based on MOS score.

        Args:
            mos: MOS score (1.0-5.0)

        Returns:
            Quality category string
        """
        if mos > 4.3:
            return "Excellent"
        elif mos >= 4.0:
            return "Good"
        elif mos >= 3.6:
            return "Fair"
        elif mos >= 3.1:
            return "Poor"
        else:
            return "Bad"

    @staticmethod
    def get_r_factor_category(r_factor: float) -> str:
        """
        Get quality category based on R-factor.

        Args:
            r_factor: R-factor score (0-100)

        Returns:
            Quality category string
        """
        if r_factor >= 90:
            return "Excellent"
        elif r_factor >= 80:
            return "Good"
        elif r_factor >= 70:
            return "Acceptable"
        elif r_factor >= 60:
            return "Poor"
        else:
            return "Unacceptable"

    @staticmethod
    def calculate_call_quality_metrics(
        packet_loss_percentage: float,
        jitter_ms: float,
        codec_name: str = "G.711 μ-law (PCMU)",
        one_way_delay_ms: float = 150,
    ) -> dict:
        """
        Calculate comprehensive call quality metrics.

        Args:
            packet_loss_percentage: Percentage of packets lost
            jitter_ms: Average jitter in milliseconds
            codec_name: Name of codec
            one_way_delay_ms: Estimated one-way delay

        Returns:
            Dictionary with MOS, R-factor, and quality assessments
        """
        # Calculate MOS using simplified model
        mos_simplified = QualityScoreCalculator.calculate_mos_simplified(
            packet_loss_percentage, jitter_ms, codec_name
        )

        # Calculate R-factor using E-Model
        r_factor = QualityScoreCalculator.calculate_r_factor(
            packet_loss_percentage, jitter_ms, one_way_delay_ms, codec_name
        )

        # Convert R-factor to MOS
        mos_e_model = QualityScoreCalculator.r_factor_to_mos(r_factor)

        # Average the two MOS calculations
        mos_average = (mos_simplified + mos_e_model) / 2.0

        return {
            "mos": mos_average,
            "mos_simplified": mos_simplified,
            "mos_e_model": mos_e_model,
            "r_factor": r_factor,
            "quality_category": QualityScoreCalculator.get_quality_category(
                mos_average
            ),
            "r_factor_category": QualityScoreCalculator.get_r_factor_category(
                r_factor
            ),
        }
