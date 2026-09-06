"""Year 2500 Multi-Modal Data Fusion Engine.

Integrates heterogeneous data streams into a unified latent representation:
- On-chain analytics (whale flows, exchange balances, staking metrics)
- Order flow & microstructure (L2/L3 order book, trade flow, toxicity)
- Macroeconomic regime (yield curves, inflation, liquidity, credit spreads)
- Sentiment & alternative data (social, news, satellite, search trends)
- Cross-asset correlations (equities, FX, commodities, rates)

All modalities fused via cross-attention into a unified trading latent space.
"""

from __future__ import annotations

import hashlib
import math
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

import numpy as np
import pandas as pd


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    if not math.isfinite(float(value)):
        return low
    return float(max(low, min(high, value)))


# ============================================================================
# Modality Encoders: Each data stream has a specialized encoder
# ============================================================================

class ModalityEncoder:
    """Base class for modality-specific encoders."""

    def __init__(self, name: str, output_dim: int, seed: int = 2500) -> None:
        self.name = name
        self.output_dim = output_dim
        self.rng = np.random.default_rng(seed + hash(name) % 10000)
        self._build_encoder()

    def _build_encoder(self) -> None:
        raise NotImplementedError

    def encode(self, data: dict[str, Any]) -> np.ndarray:
        raise NotImplementedError

    def get_output_dim(self) -> int:
        return self.output_dim


class OnChainEncoder(ModalityEncoder):
    """Encodes on-chain metrics into latent representation.

    Features: whale netflows, exchange reserves, staking ratio,
    active addresses, hash rate, funding rates, basis, perp funding.
    """

    def _build_encoder(self) -> None:
        # 15 on-chain features -> 64 dim latent
        self.feature_names = [
            "whale_netflow_btc", "whale_netflow_eth", "exchange_reserve_btc",
            "exchange_reserve_eth", "staking_ratio_eth", "staking_ratio_sol",
            "active_addresses_btc", "active_addresses_eth", "hash_rate_btc",
            "difficulty_btc", "funding_rate_btc", "funding_rate_eth",
            "basis_btc", "basis_eth", "perp_open_interest",
        ]
        in_dim = len(self.feature_names)

        # Tensor train encoder for efficiency
        self.encoder_tt = TensorTrainLayer(in_dim, self.output_dim, bond_dim=16, seed=hash(self.name))
        self.ln_gamma = np.ones(self.output_dim, dtype=np.float32)
        self.ln_beta = np.zeros(self.output_dim, dtype=np.float32)

    def encode(self, data: dict[str, Any]) -> np.ndarray:
        features = []
        for name in self.feature_names:
            val = safe_float(data.get(name))
            # Normalize
            if "netflow" in name:
                val = np.tanh(val / 10000)  # BTC units
            elif "reserve" in name:
                val = np.tanh(val / 100000)
            elif "ratio" in name:
                val = (val - 0.1) / 0.5  # 0.1 to 0.6 range
            elif "addresses" in name:
                val = np.tanh(val / 1e6)
            elif "hash" in name or "difficulty" in name:
                val = np.tanh(val / 1e20)
            elif "funding" in name or "basis" in name:
                val = np.tanh(val * 100)  # bps
            elif "open_interest" in name:
                val = np.tanh(val / 1e9)
            features.append(clamp(val, -1.0, 1.0))

        x = np.array(features, dtype=np.float32)
        encoded = self.encoder_tt.forward(x[None, :])[0]
        # Layer norm
        mean = encoded.mean()
        var = encoded.var()
        encoded = (encoded - mean) / math.sqrt(var + 1e-5) * self.ln_gamma + self.ln_beta
        return encoded


class OrderFlowEncoder(ModalityEncoder):
    """Encodes high-frequency order flow and microstructure features.

    Features: bid-ask imbalance, trade flow toxicity (VPIN), order book
    depth asymmetry, large trade detection, spread dynamics, queue position.
    """

    def _build_encoder(self) -> None:
        self.feature_names = [
            "bid_ask_imbalance", "trade_flow_imbalance", "vpin",
            "book_depth_asymmetry", "large_trade_ratio", "spread_bps",
            "spread_volatility", "queue_position_bid", "queue_position_ask",
            "order_arrival_rate", "cancellation_rate", "effective_spread",
            "realized_spread", "price_impact_1m", "price_impact_5m",
        ]
        in_dim = len(self.feature_names)

        self.encoder_tt = TensorTrainLayer(in_dim, self.output_dim, bond_dim=16, seed=hash(self.name))
        self.ln_gamma = np.ones(self.output_dim, dtype=np.float32)
        self.ln_beta = np.zeros(self.output_dim, dtype=np.float32)

    def encode(self, data: dict[str, Any]) -> np.ndarray:
        features = []
        for name in self.feature_names:
            val = safe_float(data.get(name))
            if "imbalance" in name or "asymmetry" in name:
                val = clamp(val, -1.0, 1.0)
            elif "vpin" in name or "ratio" in name or "rate" in name:
                val = clamp(val, 0.0, 1.0)
            elif "spread" in name or "impact" in name:
                val = np.tanh(val * 100)  # bps
            features.append(val)

        x = np.array(features, dtype=np.float32)
        encoded = self.encoder_tt.forward(x[None, :])[0]
        mean = encoded.mean()
        var = encoded.var()
        encoded = (encoded - mean) / math.sqrt(var + 1e-5) * self.ln_gamma + self.ln_beta
        return encoded


class MacroEncoder(ModalityEncoder):
    """Encodes macroeconomic regime indicators.

    Features: yield curve slope, inflation breakevens, DXY, VIX,
    credit spreads, money supply growth, central bank balance sheet,
    term premium, real rates, financial conditions index.
    """

    def _build_encoder(self) -> None:
        self.feature_names = [
            "yield_curve_2s10s", "yield_curve_3m10y", "inflation_breakeven_5y",
            "inflation_breakeven_10y", "dxy", "vix", "move_index",
            "credit_spread_ig", "credit_spread_hy", "m2_growth_yoy",
            "fed_balance_sheet", "ecb_balance_sheet", "term_premium_10y",
            "real_rate_5y", "real_rate_10y", "financial_conditions_index",
            "repo_rate_sofr", "repo_rate_eonia", "teda_spread", "swap_spread_10y",
        ]
        in_dim = len(self.feature_names)

        self.encoder_tt = TensorTrainLayer(in_dim, self.output_dim, bond_dim=16, seed=hash(self.name))
        self.ln_gamma = np.ones(self.output_dim, dtype=np.float32)
        self.ln_beta = np.zeros(self.output_dim, dtype=np.float32)

    def encode(self, data: dict[str, Any]) -> np.ndarray:
        features = []
        for name in self.feature_names:
            val = safe_float(data.get(name))
            if "yield_curve" in name or "spread" in name:
                val = np.tanh(val * 100)  # bps
            elif "inflation" in name:
                val = (val - 2.0) / 3.0  # centered at 2%
            elif "dxy" in name:
                val = (val - 100) / 15  # centered at 100
            elif "vix" in name or "move" in name:
                val = np.tanh((val - 15) / 20)
            elif "growth" in name or "balance" in name:
                val = np.tanh(val / 100)
            elif "rate" in name or "premium" in name:
                val = np.tanh(val * 100)
            elif "conditions" in name:
                val = clamp(val, -3.0, 3.0) / 3.0
            features.append(clamp(val, -1.0, 1.0))

        x = np.array(features, dtype=np.float32)
        encoded = self.encoder_tt.forward(x[None, :])[0]
        mean = encoded.mean()
        var = encoded.var()
        encoded = (encoded - mean) / math.sqrt(var + 1e-5) * self.ln_gamma + self.ln_beta
        return encoded


class SentimentEncoder(ModalityEncoder):
    """Encodes sentiment and alternative data.

    Features: social sentiment (Twitter/Reddit), news sentiment,
    Google Trends, satellite data (parking lots, shipping), app rankings,
    developer activity, governance participation.
    """

    def _build_encoder(self) -> None:
        self.feature_names = [
            "social_sentiment_btc", "social_sentiment_eth", "social_volume_btc",
            "social_volume_eth", "news_sentiment_crypto", "news_volume_crypto",
            "google_trends_btc", "google_trends_eth", "google_trends_crypto",
            "satellite_shipping_index", "satellite_parking_index", "app_store_ranking",
            "github_commits_btc", "github_commits_eth", "github_stars_defi",
            "governance_participation", "dao_treasury_growth", "stablecoin_supply_growth",
            "defi_tvl_growth", "nft_volume_growth",
        ]
        in_dim = len(self.feature_names)

        self.encoder_tt = TensorTrainLayer(in_dim, self.output_dim, bond_dim=16, seed=hash(self.name))
        self.ln_gamma = np.ones(self.output_dim, dtype=np.float32)
        self.ln_beta = np.zeros(self.output_dim, dtype=np.float32)

    def encode(self, data: dict[str, Any]) -> np.ndarray:
        features = []
        for name in self.feature_names:
            val = safe_float(data.get(name))
            if "sentiment" in name:
                val = clamp(val, -1.0, 1.0)
            elif "volume" in name or "trends" in name or "ranking" in name:
                val = np.tanh(val / 100)
            elif "commits" in name or "stars" in name:
                val = np.tanh(val / 1000)
            elif "participation" in name or "growth" in name:
                val = np.tanh(val * 10)
            features.append(clamp(val, -1.0, 1.0))

        x = np.array(features, dtype=np.float32)
        encoded = self.encoder_tt.forward(x[None, :])[0]
        mean = encoded.mean()
        var = encoded.var()
        encoded = (encoded - mean) / math.sqrt(var + 1e-5) * self.ln_gamma + self.ln_beta
        return encoded


class CrossAssetEncoder(ModalityEncoder):
    """Encodes cross-asset correlations and regime indicators.

    Features: equity returns (SPX, NDX), FX returns (DXY, major pairs),
    commodity returns (oil, gold, copper), vol surfaces, correlation regimes,
    risk-on/off indicators, carry trade metrics.
    """

    def _build_encoder(self) -> None:
        self.feature_names = [
            "spx_return_1d", "spx_return_5d", "ndx_return_1d", "ndx_return_5d",
            "dxy_return_1d", "dxy_return_5d", "eurusd_return_1d", "usdjpy_return_1d",
            "gold_return_1d", "gold_return_5d", "oil_return_1d", "oil_return_5d",
            "copper_return_1d", "vix_level", "vix_term_structure",
            "skew_index", "corr_spx_btc", "corr_spx_eth", "corr_gold_btc",
            "risk_on_off_score", "carry_trade_index", "em_fx_index",
            "commodity_index", "credit_spread_change", "rate_change_2y",
            "rate_change_10y", "yield_curve_change",
        ]
        in_dim = len(self.feature_names)

        self.encoder_tt = TensorTrainLayer(in_dim, self.output_dim, bond_dim=16, seed=hash(self.name))
        self.ln_gamma = np.ones(self.output_dim, dtype=np.float32)
        self.ln_beta = np.zeros(self.output_dim, dtype=np.float32)

    def encode(self, data: dict[str, Any]) -> np.ndarray:
        features = []
        for name in self.feature_names:
            val = safe_float(data.get(name))
            if "return" in name:
                val = np.tanh(val * 100)  # daily returns in %
            elif "vix" in name or "skew" in name:
                val = np.tanh((val - 20) / 30)
            elif "corr" in name:
                val = clamp(val, -1.0, 1.0)
            elif "score" in name or "index" in name:
                val = clamp(val, -1.0, 1.0)
            elif "change" in name:
                val = np.tanh(val * 100)  # bps
            features.append(clamp(val, -1.0, 1.0))

        x = np.array(features, dtype=np.float32)
        encoded = self.encoder_tt.forward(x[None, :])[0]
        mean = encoded.mean()
        var = encoded.var()
        encoded = (encoded - mean) / math.sqrt(var + 1e-5) * self.ln_gamma + self.ln_beta
        return encoded


# ============================================================================
# Tensor Train Layer (reused from neural_2500)
# ============================================================================

class TensorTrainLayer:
    """Tensor Train (Matrix Product State) layer for exponential compression."""

    def __init__(
        self,
        input_dim: int,
        output_dim: int,
        bond_dim: int = 32,
        seed: int = 2500,
    ) -> None:
        self.input_dim = input_dim
        self.output_dim = output_dim
        self.bond_dim = bond_dim
        self.rng = np.random.default_rng(seed)

        self.in_factors = self._factorize(input_dim)
        self.out_factors = self._factorize(output_dim)
        self.num_cores = len(self.in_factors)

        self.cores: list[np.ndarray] = []
        prev_bond = 1
        for i in range(self.num_cores):
            in_f = self.in_factors[i]
            out_f = self.out_factors[i]
            next_bond = bond_dim if i < self.num_cores - 1 else 1
            scale = math.sqrt(2.0 / (prev_bond * in_f * out_f * next_bond))
            core = self.rng.normal(0.0, scale * 0.1, (prev_bond, in_f, out_f, next_bond)).astype(np.float32)
            self.cores.append(core)
            prev_bond = next_bond

        self.bias = np.zeros(output_dim, dtype=np.float32)

    def _factorize(self, dim: int) -> list[int]:
        factors = []
        d = dim
        for p in [2, 3, 5, 7, 11, 13]:
            while d % p == 0 and d > p:
                factors.append(p)
                d //= p
        if d > 1:
            factors.append(d)
        if not factors:
            factors = [dim]
        while len(factors) < 3:
            factors.append(1)
        return factors[:6]

    def forward(self, x: np.ndarray) -> np.ndarray:
        batch_mode = x.ndim == 2
        if not batch_mode:
            x = x[None, :]

        batch_size = x.shape[0]
        x_reshaped = x.reshape(batch_size, *self.in_factors)

        result = x_reshaped
        for i, core in enumerate(self.cores):
            in_f = self.in_factors[i]
            out_f = self.out_factors[i]
            result = result.reshape(batch_size, -1, in_f)
            result = np.einsum('bki,kioj->bjo', result, core)
            result = result.reshape(batch_size, -1)

        result = result.reshape(batch_size, self.output_dim) + self.bias
        return result[0] if not batch_mode else result

    def get_param_count(self) -> int:
        return sum(core.size for core in self.cores) + self.bias.size


# ============================================================================
# Cross-Modal Fusion: Attention-based integration
# ============================================================================

class CrossModalFusion:
    """Fuses multiple modalities via cross-attention into unified latent space.

    Uses multi-head attention where each modality attends to all others,
    creating a rich joint representation that captures cross-modal interactions.
    """

    def __init__(
        self,
        modality_dims: dict[str, int],
        fusion_dim: int = 256,
        num_heads: int = 8,
        seed: int = 2500,
    ) -> None:
        self.modality_names = list(modality_dims.keys())
        self.modality_dims = modality_dims
        self.fusion_dim = fusion_dim
        self.num_heads = num_heads
        self.head_dim = fusion_dim // num_heads
        self.rng = np.random.default_rng(seed)

        # Project each modality to fusion_dim
        self.projections: dict[str, TensorTrainLayer] = {}
        for name, dim in modality_dims.items():
            self.projections[name] = TensorTrainLayer(dim, fusion_dim, bond_dim=32, seed=seed + hash(name) % 1000)

        # Cross-attention weights (shared across modalities)
        self.q_proj = self.rng.normal(0, 0.02, (fusion_dim, fusion_dim)).astype(np.float32)
        self.k_proj = self.rng.normal(0, 0.02, (fusion_dim, fusion_dim)).astype(np.float32)
        self.v_proj = self.rng.normal(0, 0.02, (fusion_dim, fusion_dim)).astype(np.float32)
        self.out_proj = self.rng.normal(0, 0.02, (fusion_dim, fusion_dim)).astype(np.float32)

        # Modality-specific gating (learn which modalities to trust)
        self.modality_gates: dict[str, np.ndarray] = {}
        for name in self.modality_names:
            self.modality_gates[name] = self.rng.normal(0, 0.1, (fusion_dim,)).astype(np.float32)

        # Final fusion layer
        self.fusion_tt = TensorTrainLayer(fusion_dim, fusion_dim, bond_dim=32, seed=seed + 999)
        self.ln_gamma = np.ones(fusion_dim, dtype=np.float32)
        self.ln_beta = np.zeros(fusion_dim, dtype=np.float32)

    def forward(self, modality_outputs: dict[str, np.ndarray]) -> np.ndarray:
        """Fuse modality outputs via cross-attention.

        Args:
            modality_outputs: Dict of {modality_name: [output_dim]} vectors

        Returns:
            Fused representation [fusion_dim]
        """
        # Project all modalities to fusion_dim
        projected = {}
        for name, vec in modality_outputs.items():
            if name in self.projections:
                projected[name] = self.projections[name].forward(vec[None, :])[0]
            else:
                # Pad or truncate
                v = vec[:self.fusion_dim] if len(vec) >= self.fusion_dim else np.pad(vec, (0, self.fusion_dim - len(vec)))
                projected[name] = v

        # Stack: [num_modalities, fusion_dim]
        modality_list = [projected[name] for name in self.modality_names if name in projected]
        if not modality_list:
            return np.zeros(self.fusion_dim, dtype=np.float32)

        stacked = np.stack(modality_list, axis=0)  # [M, D]
        M, D = stacked.shape

        # Apply modality gates
        for i, name in enumerate(self.modality_names):
            if name in projected:
                gate = 1.0 / (1.0 + np.exp(-self.modality_gates[name]))
                stacked[i] *= gate

        # Self-attention across modalities
        Q = stacked @ self.q_proj  # [M, D]
        K = stacked @ self.k_proj
        V = stacked @ self.v_proj

        # Reshape for multi-head
        Q = Q.reshape(M, self.num_heads, self.head_dim).transpose(1, 0, 2)  # [H, M, d]
        K = K.reshape(M, self.num_heads, self.head_dim).transpose(1, 0, 2)
        V = V.reshape(M, self.num_heads, self.head_dim).transpose(1, 0, 2)

        # Attention scores
        scale = self.head_dim ** -0.5
        scores = np.matmul(Q, K.transpose(0, 2, 1)) * scale  # [H, M, M]
        attn_weights = self._softmax(scores, axis=-1)

        # Apply attention
        out = np.matmul(attn_weights, V)  # [H, M, d]
        out = out.transpose(1, 0, 2).reshape(M, D)  # [M, D]

        # Output projection
        out = out @ self.out_proj

        # Aggregate across modalities (weighted by gate magnitudes)
        gate_mags = np.array([np.mean(np.abs(1.0 / (1.0 + np.exp(-self.modality_gates[name])))
                               for name in self.modality_names if name in projected])
        gate_mags = gate_mags / (gate_mags.sum() + 1e-8)

        fused = np.sum(out * gate_mags[:, None], axis=0)

        # Final fusion layer
        fused = self.fusion_tt.forward(fused[None, :])[0]

        # Layer norm
        mean = fused.mean()
        var = fused.var()
        fused = (fused - mean) / math.sqrt(var + 1e-5) * self.ln_gamma + self.ln_beta

        return fused

    def _softmax(self, x: np.ndarray, axis: int = -1) -> np.ndarray:
        x_max = np.max(x, axis=axis, keepdims=True)
        exp_x = np.exp(x - x_max)
        return exp_x / (np.sum(exp_x, axis=axis, keepdims=True) + 1e-8)


# ============================================================================
# Multi-Modal Fusion Engine: Main Interface
# ============================================================================

@dataclass
class MultiModalState:
    """State of the multi-modal fusion engine."""
    modality_latents: dict[str, np.ndarray]
    fused_latent: np.ndarray
    modality_weights: dict[str, float]
    timestamp: str
    data_quality: dict[str, float]


class MultiModalFusionEngine:
    """Main engine for multi-modal data fusion in Year 2500 trading organism.

    Orchestrates all modality encoders, cross-modal fusion, and provides
    a unified latent representation for the cortex.
    """

    def __init__(
        self,
        latent_dim: int = 256,
        seed: int = 2500,
    ) -> None:
        self.latent_dim = latent_dim
        self.seed = seed
        self.rng = np.random.default_rng(seed)

        # Initialize modality encoders
        modality_dims = {
            "onchain": 64,
            "orderflow": 64,
            "macro": 64,
            "sentiment": 64,
            "crossasset": 64,
        }

        self.encoders: dict[str, ModalityEncoder] = {
            "onchain": OnChainEncoder("onchain", 64, seed),
            "orderflow": OrderFlowEncoder("orderflow", 64, seed + 1),
            "macro": MacroEncoder("macro", 64, seed + 2),
            "sentiment": SentimentEncoder("sentiment", 64, seed + 3),
            "crossasset": CrossAssetEncoder("crossasset", 64, seed + 4),
        }

        # Cross-modal fusion
        self.fusion = CrossModalFusion(modality_dims, fusion_dim=latent_dim, num_heads=8, seed=seed)

        # Data quality tracking
        self.data_quality: dict[str, float] = {name: 1.0 for name in modality_dims}
        self.last_update: dict[str, float] = {name: 0.0 for name in modality_dims}

        # History for temporal modeling
        self.fused_history: list[np.ndarray] = []
        self.max_history = 100

        # Regime detection on fused latent
        self.regime_clusters: list[np.ndarray] = []
        self.regime_labels: list[int] = []

    def update(self, market_data: dict[str, Any]) -> MultiModalState:
        """Update all modalities with new data and produce fused latent."""
        modality_latents = {}

        # Encode each modality
        for name, encoder in self.encoders.items():
            try:
                modality_data = market_data.get(name, {})
                latent = encoder.encode(modality_data)
                modality_latents[name] = latent

                # Update data quality (based on data freshness/completeness)
                self._update_quality(name, modality_data)
            except Exception as e:
                # Fallback: zeros with low quality
                modality_latents[name] = np.zeros(encoder.get_output_dim(), dtype=np.float32)
                self.data_quality[name] *= 0.95

        # Cross-modal fusion
        fused_latent = self.fusion.forward(modality_latents)

        # Update history
        self.fused_history.append(fused_latent)
        if len(self.fused_history) > self.max_history:
            self.fused_history = self.fused_history[-self.max_history:]

        # Compute modality weights (attention gate magnitudes)
        modality_weights = {}
        for name in self.modality_names:
            gate = self.fusion.modality_gates.get(name, np.zeros(self.latent_dim))
            weight = float(np.mean(1.0 / (1.0 + np.exp(-gate))))
            modality_weights[name] = weight * self.data_quality.get(name, 1.0)

        # Detect regime on fused latent
        regime = self._detect_regime(fused_latent)

        state = MultiModalState(
            modality_latents=modality_latents,
            fused_latent=fused_latent,
            modality_weights=modality_weights,
            timestamp=utc_now().isoformat(),
            data_quality=self.data_quality.copy(),
        )

        return state

    def _update_quality(self, modality: str, data: dict[str, Any]) -> None:
        """Update data quality score based on completeness and freshness."""
        expected_keys = self.encoders[modality].feature_names
        present = sum(1 for k in expected_keys if k in data and data[k] is not None)
        completeness = present / len(expected_keys)

        # Freshness: time since last update
        now = time.time()
        freshness = 1.0
        if self.last_update[modality] > 0:
            age = now - self.last_update[modality]
            freshness = np.exp(-age / 300.0)  # 5 min half-life

        self.data_quality[modality] = 0.7 * completeness + 0.3 * freshness
        self.last_update[modality] = now

    def _detect_regime(self, latent: np.ndarray) -> int:
        """Simple online clustering for regime detection."""
        if len(self.regime_clusters) < 5:
            self.regime_clusters.append(latent.copy())
            self.regime_labels.append(len(self.regime_clusters) - 1)
            return len(self.regime_clusters) - 1

        # Find nearest cluster
        dists = [np.linalg.norm(latent - c) for c in self.regime_clusters]
        nearest = int(np.argmin(dists))

        # Update cluster center (exponential moving average)
        alpha = 0.05
        self.regime_clusters[nearest] = (1 - alpha) * self.regime_clusters[nearest] + alpha * latent

        return nearest

    def get_fused_history(self) -> np.ndarray:
        """Get history of fused latents for temporal modeling."""
        if not self.fused_history:
            return np.zeros((1, self.latent_dim), dtype=np.float32)
        return np.stack(self.fused_history, axis=0)

    def get_modality_contributions(self) -> dict[str, float]:
        """Get relative contribution of each modality to fused latent."""
        return self.fusion.modality_gates.copy() if hasattr(self.fusion, 'modality_gates') else {}

    def get_state_dict(self) -> dict[str, Any]:
        """Get serializable state."""
        return {
            "latent_dim": self.latent_dim,
            "data_quality": self.data_quality,
            "modality_weights": {k: float(v) for k, v in self.get_modality_contributions().items()},
            "num_regimes": len(self.regime_clusters),
            "history_length": len(self.fused_history),
        }


# ============================================================================
# Data Providers: Interfaces for real data ingestion
# ============================================================================

class DataProvider:
    """Base class for data providers."""

    def fetch(self) -> dict[str, Any]:
        raise NotImplementedError

    def get_schema(self) -> dict[str, str]:
        """Return expected feature names and types."""
        raise NotImplementedError


class SyntheticDataProvider(DataProvider):
    """Synthetic data provider for testing and development."""

    def __init__(self, seed: int = 2500) -> None:
        self.rng = np.random.default_rng(seed)
        self.counter = 0

    def fetch(self) -> dict[str, Any]:
        """Generate synthetic multi-modal data."""
        self.counter += 1
        t = self.counter / 100.0

        # Correlated regime
        regime = math.sin(t * 0.1) * 0.5 + math.sin(t * 0.03) * 0.3
        noise = self.rng.normal(0, 0.1)

        return {
            "onchain": {
                "whale_netflow_btc": regime * 5000 + noise * 1000,
                "whale_netflow_eth": regime * 30000 + noise * 5000,
                "exchange_reserve_btc": 2_500_000 + regime * 100_000 + noise * 10_000,
                "exchange_reserve_eth": 18_000_000 + regime * 500_000 + noise * 50_000,
                "staking_ratio_eth": 0.25 + regime * 0.1 + noise * 0.02,
                "staking_ratio_sol": 0.35 + regime * 0.05 + noise * 0.01,
                "active_addresses_btc": 800_000 + regime * 100_000 + noise * 20_000,
                "active_addresses_eth": 500_000 + regime * 80_000 + noise * 15_000,
                "hash_rate_btc": 600e18 + regime * 50e18 + noise * 5e18,
                "difficulty_btc": 80e12 + regime * 10e12 + noise * 1e12,
                "funding_rate_btc": regime * 0.01 + noise * 0.002,
                "funding_rate_eth": regime * 0.015 + noise * 0.003,
                "basis_btc": regime * 100 + noise * 20,
                "basis_eth": regime * 80 + noise * 15,
                "perp_open_interest": 15e9 + regime * 2e9 + noise * 0.5e9,
            },
            "orderflow": {
                "bid_ask_imbalance": regime * 0.3 + noise * 0.1,
                "trade_flow_imbalance": regime * 0.2 + noise * 0.1,
                "vpin": 0.3 + regime * 0.2 + noise * 0.05,
                "book_depth_asymmetry": regime * 0.15 + noise * 0.05,
                "large_trade_ratio": 0.15 + regime * 0.1 + noise * 0.02,
                "spread_bps": 2.0 + noise * 1.0,
                "spread_volatility": 0.5 + noise * 0.2,
                "queue_position_bid": 0.5 + regime * 0.1 + noise * 0.05,
                "queue_position_ask": 0.5 - regime * 0.1 + noise * 0.05,
                "order_arrival_rate": 1000 + regime * 200 + noise * 100,
                "cancellation_rate": 0.8 + noise * 0.1,
                "effective_spread": 1.5 + noise * 0.5,
                "realized_spread": 0.8 + noise * 0.3,
                "price_impact_1m": 5.0 + noise * 2.0,
                "price_impact_5m": 12.0 + noise * 5.0,
            },
            "macro": {
                "yield_curve_2s10s": 50 + regime * 30 + noise * 10,
                "yield_curve_3m10y": 80 + regime * 40 + noise * 15,
                "inflation_breakeven_5y": 2.3 + regime * 0.3 + noise * 0.1,
                "inflation_breakeven_10y": 2.4 + regime * 0.2 + noise * 0.1,
                "dxy": 103 + regime * 3 + noise * 1,
                "vix": 16 + regime * 5 + noise * 2,
                "move_index": 80 + regime * 20 + noise * 10,
                "credit_spread_ig": 100 + regime * 30 + noise * 10,
                "credit_spread_hy": 350 + regime * 100 + noise * 30,
                "m2_growth_yoy": 0.5 + regime * 2 + noise * 0.5,
                "fed_balance_sheet": 7.2 + regime * 0.3 + noise * 0.1,
                "ecb_balance_sheet": 6.5 + regime * 0.2 + noise * 0.1,
                "term_premium_10y": 30 + regime * 20 + noise * 5,
                "real_rate_5y": 1.8 + regime * 0.5 + noise * 0.2,
                "real_rate_10y": 2.0 + regime * 0.4 + noise * 0.2,
                "financial_conditions_index": 0.0 + regime * 0.5 + noise * 0.2,
                "repo_rate_sofr": 5.3 + noise * 0.05,
                "repo_rate_eonia": 3.8 + noise * 0.05,
                "teda_spread": 15 + noise * 5,
                "swap_spread_10y": 5 + regime * 5 + noise * 2,
            },
            "sentiment": {
                "social_sentiment_btc": regime * 0.4 + noise * 0.2,
                "social_sentiment_eth": regime * 0.3 + noise * 0.2,
                "social_volume_btc": 50000 + regime * 20000 + noise * 5000,
                "social_volume_eth": 30000 + regime * 15000 + noise * 3000,
                "news_sentiment_crypto": regime * 0.2 + noise * 0.15,
                "news_volume_crypto": 2000 + regime * 500 + noise * 200,
                "google_trends_btc": 50 + regime * 20 + noise * 10,
                "google_trends_eth": 40 + regime * 15 + noise * 8,
                "google_trends_crypto": 30 + regime * 10 + noise * 5,
                "satellite_shipping_index": 100 + regime * 10 + noise * 3,
                "satellite_parking_index": 80 + regime * 15 + noise * 5,
                "app_store_ranking": 100 + noise * 50,
                "github_commits_btc": 50 + regime * 10 + noise * 5,
                "github_commits_eth": 80 + regime * 15 + noise * 8,
                "github_stars_defi": 2000 + regime * 500 + noise * 100,
                "governance_participation": 0.15 + regime * 0.1 + noise * 0.02,
                "dao_treasury_growth": 0.05 + regime * 0.03 + noise * 0.01,
                "stablecoin_supply_growth": 0.02 + regime * 0.01 + noise * 0.005,
                "defi_tvl_growth": 0.03 + regime * 0.02 + noise * 0.01,
                "nft_volume_growth": -0.1 + regime * 0.2 + noise * 0.05,
            },
            "crossasset": {
                "spx_return_1d": regime * 0.5 + noise * 0.3,
                "spx_return_5d": regime * 2.0 + noise * 1.0,
                "ndx_return_1d": regime * 0.7 + noise * 0.4,
                "ndx_return_5d": regime * 2.5 + noise * 1.2,
                "dxy_return_1d": -regime * 0.2 + noise * 0.15,
                "dxy_return_5d": -regime * 0.8 + noise * 0.5,
                "eurusd_return_1d": regime * 0.2 + noise * 0.15,
                "usdjpy_return_1d": -regime * 0.3 + noise * 0.2,
                "gold_return_1d": -regime * 0.3 + noise * 0.2,
                "gold_return_5d": -regime * 1.0 + noise * 0.8,
                "oil_return_1d": regime * 0.8 + noise * 0.5,
                "oil_return_5d": regime * 3.0 + noise * 2.0,
                "copper_return_1d": regime * 0.6 + noise * 0.4,
                "vix_level": 16 + regime * 5 + noise * 2,
                "vix_term_structure": 0.1 + regime * 0.05 + noise * 0.02,
                "skew_index": 130 + regime * 10 + noise * 5,
                "corr_spx_btc": 0.3 + regime * 0.3 + noise * 0.1,
                "corr_spx_eth": 0.4 + regime * 0.3 + noise * 0.1,
                "corr_gold_btc": -0.1 + regime * 0.2 + noise * 0.1,
                "risk_on_off_score": regime,
                "carry_trade_index": 100 + regime * 10 + noise * 3,
                "em_fx_index": 100 + regime * 5 + noise * 2,
                "commodity_index": 100 + regime * 8 + noise * 3,
                "credit_spread_change": regime * 5 + noise * 2,
                "rate_change_2y": regime * 3 + noise * 1,
                "rate_change_10y": regime * 4 + noise * 1.5,
                "yield_curve_change": regime * 2 + noise * 1,
            },
        }

    def get_schema(self) -> dict[str, str]:
        schemas = {}
        for encoder in [OnChainEncoder, OrderFlowEncoder, MacroEncoder, SentimentEncoder, CrossAssetEncoder]:
            instance = encoder("", 64, 0)
            for name in instance.feature_names:
                schemas[name] = "float"
        return schemas


# ============================================================================
# Factory and Integration
# ============================================================================

def create_multimodal_engine(latent_dim: int = 256, seed: int = 2500) -> MultiModalFusionEngine:
    """Factory to create multi-modal fusion engine."""
    return MultiModalFusionEngine(latent_dim=latent_dim, seed=seed)


def create_synthetic_provider(seed: int = 2500) -> SyntheticDataProvider:
    """Factory for synthetic data provider."""
    return SyntheticDataProvider(seed=seed)


if __name__ == "__main__":
    # Test
    engine = create_multimodal_engine()
    provider = create_synthetic_provider()

    for i in range(3):
        data = provider.fetch()
        state = engine.update(data)
        print(f"\nStep {i+1}:")
        print(f"  Fused latent shape: {state.fused_latent.shape}")
        print(f"  Modality weights: {state.modality_weights}")
        print(f"  Data quality: {state.data_quality}")

    print(f"\nEngine state: {engine.get_state_dict()}")