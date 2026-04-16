"""Pipeline orchestrator — runs the full PIR generation pipeline.

Coordinates all analysis steps from input parsing through PIR output.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cti_primer.analysis.asset_mapper import map_assets
from cti_primer.analysis.element_extractor import detect_triggers, extract_elements
from cti_primer.analysis.pir_clusterer import cluster_threats
from cti_primer.analysis.risk_scorer import score_risks
from cti_primer.analysis.threat_mapper import map_threats
from cti_primer.config import Config
from cti_primer.generator.assets_generator import generate_assets
from cti_primer.generator.pir_builder import build_pirs
from cti_primer.generator.report_builder import build_report
from cti_primer.ingest.context_parser import parse_file
from cti_primer.llm.client import HttpxLLMClient, LLMClient, NoLLMClient
from cti_primer.models import (
    AssetTag,
    BusinessContext,
    BusinessElement,
    PIROutput,
    RiskScore,
    ThreatCluster,
    ThreatProfile,
)

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Complete result from a pipeline run."""

    context: BusinessContext
    elements: list[BusinessElement]
    triggers: list[str]
    assets: list[AssetTag]
    threats: list[ThreatProfile]
    scores: list[RiskScore]
    clusters: list[ThreatCluster]
    pir: PIROutput
    report: str


def create_llm_client(config: Config, *, no_llm: bool = False) -> LLMClient:
    """Create the appropriate LLM client based on mode."""
    if no_llm:
        return NoLLMClient()
    return HttpxLLMClient(config.llm)


def run_pipeline(
    input_path: Path,
    config: Config,
    *,
    no_llm: bool = False,
    sage_observations: dict[str, int] | None = None,
) -> PipelineResult:
    """Execute the full PIR generation pipeline.

    Steps:
      1. Ingest: parse input → BusinessContext
      2. Extract: flatten context → BusinessElements + triggers
      3. Map assets: elements → AssetTags
      4. Map threats: industry × geography → ThreatProfiles
      5. Score risks: likelihood × impact → RiskScores
      6. Cluster: group threats → ThreatClusters
      7. Build PIR: clusters → PIROutput
      8. Build report: collection plan Markdown

    Args:
        input_path: Path to JSON or Markdown input file.
        config: Application configuration.
        no_llm: If True, use dictionary-only mode.
        sage_observations: Optional SAGE observation data.

    Returns:
        PipelineResult with all intermediate and final outputs.
    """
    llm: LLMClient | None = None if no_llm else create_llm_client(config)

    # 1. Ingest
    logger.info("Step 1: Parsing input from %s", input_path)
    context = parse_file(input_path, llm=llm)

    # 2. Extract elements and triggers
    logger.info("Step 2: Extracting business elements")
    elements = extract_elements(context)
    triggers = detect_triggers(context)
    logger.info("  Found %d elements, %d triggers", len(elements), len(triggers))

    # 3. Map assets
    logger.info("Step 3: Mapping assets")
    assets = map_assets(elements, context, llm=llm)
    logger.info("  Mapped %d asset tags", len(assets))

    # 4. Map threats
    logger.info("Step 4: Mapping threats")
    threats = map_threats(
        context.organization.industry,
        context.organization.geography,
        triggers,
        llm=llm,
    )
    logger.info("  Matched %d threat profiles", len(threats))

    # 5. Score risks
    logger.info("Step 5: Scoring risks")
    scores = score_risks(
        context,
        threats,
        assets,
        triggers,
        sage_observations=sage_observations,
    )

    # 6. Cluster threats
    logger.info("Step 6: Clustering threats")
    clusters = cluster_threats(threats, scores)
    logger.info("  Created %d clusters", len(clusters))

    # 7. Build PIR
    logger.info("Step 7: Building PIRs")
    pir = build_pirs(context, clusters, scores, assets, llm=llm)
    logger.info("  Generated %d PIR items", len(pir.pir_items))

    # 8. Build report
    logger.info("Step 8: Building collection plan")
    report = build_report(context, pir, clusters, scores)

    # Cleanup
    if isinstance(llm, HttpxLLMClient):
        llm.close()

    return PipelineResult(
        context=context,
        elements=elements,
        triggers=triggers,
        assets=assets,
        threats=threats,
        scores=scores,
        clusters=clusters,
        pir=pir,
        report=report,
    )


def run_assets_pipeline(
    input_path: Path,
    config: Config,
    *,
    no_llm: bool = False,
) -> dict[str, Any]:
    """Run the asset generation pipeline only.

    Args:
        input_path: Path to JSON or Markdown input.
        config: Application configuration.
        no_llm: Dictionary-only mode.

    Returns:
        SAGE-compatible assets dict.
    """
    llm: LLMClient | None = None if no_llm else create_llm_client(config)

    context = parse_file(input_path, llm=llm)
    result = generate_assets(context)

    if isinstance(llm, HttpxLLMClient):
        llm.close()

    return result
