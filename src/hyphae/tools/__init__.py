"""External tool wrappers (one tool, one module).

Tools are registered via :class:`hyphae.tools.registry.ToolRegistry`. Agents
never import wrappers directly.
"""

from .antismash import AntiSmashWebClient, LocalAntiSmash, parse_antismash_json
from .assemblers import Megahit, MetaSpades, fasta_assembly_stats
from .base import Tool, ToolRunResult, ToolUnavailable, run_shell
from .binners import CONCOCT, DASTool, MetaBAT2
from .fastp import Fastp
from .qc import Busco, CheckM2, EukRep
from .registry import BUILTIN_TOOL_MAPPINGS, ToolEntry, ToolRegistry
from .sra import FasterqDump, LocalFastqAdapter
from .sra_download import SraDownloadTool

__all__ = [
    "CONCOCT",
    "AntiSmashWebClient",
    "Busco",
    "CheckM2",
    "DASTool",
    "EukRep",
    "FasterqDump",
    "Fastp",
    "LocalAntiSmash",
    "LocalFastqAdapter",
    "Megahit",
    "MetaBAT2",
    "MetaSpades",
    "Tool",
    "ToolEntry",
    "ToolRegistry",
    "ToolRunResult",
    "ToolUnavailable",
    "fasta_assembly_stats",
    "parse_antismash_json",
    "run_shell",
]


def default_registry() -> ToolRegistry:
    """Build a registry that prefers hosted clients then falls back to local
    binaries. Local fastq adapter is always registered so local-FASTQ samples
    work without the SRA toolkit."""

    reg = ToolRegistry()
    reg.register(LocalFastqAdapter())
    reg.register(FasterqDump())
    reg.register(Fastp())
    reg.register(MetaSpades())
    reg.register(Megahit())
    reg.register(BUILTIN_TOOL_MAPPINGS["assembly.megahit"])
    reg.register(MetaBAT2())
    reg.register(CONCOCT())
    reg.register(DASTool())
    reg.register(CheckM2())
    reg.register(Busco())
    reg.register(EukRep())
    reg.register(AntiSmashWebClient(), prepend=True)
    reg.register(LocalAntiSmash())
    reg.register(SraDownloadTool())
    class ReadsFetchAlias(SraDownloadTool):
        tool_id = "reads.fetch"
    reg.register(ReadsFetchAlias(), prepend=True)
    return reg
