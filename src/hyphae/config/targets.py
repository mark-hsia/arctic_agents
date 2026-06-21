"""v1 antifungal target pack.

Used by the (yet-to-arrive) Target & Docking agent. Defined here now so the
Coordinator's intent validation can reject targets outside the supported set
and so the eval harness can plan its September deliverable.
"""

from __future__ import annotations

from ..state import TargetPathogen, TargetProtein

ANTIFUNGAL_TARGET_PACK: dict[TargetPathogen, list[TargetProtein]] = {
    TargetPathogen.candida_albicans: [
        TargetProtein(
            name="CYP51 (lanosterol 14alpha-demethylase)",
            pdb_id="5V5Z",
            uniprot_id="P10613",
            notes="Azole-class target.",
        ),
        TargetProtein(
            name="beta-1,3-glucan synthase (Fks1)",
            pdb_id=None,
            uniprot_id="P38624",
            notes="Echinocandin-class target.",
        ),
        TargetProtein(
            name="Hsp90",
            pdb_id="2VW5",
            uniprot_id="P46598",
            notes="Exploratory; chaperone modulator route.",
        ),
        TargetProtein(
            name="Erg1 (squalene epoxidase)",
            pdb_id=None,
            uniprot_id="P32476",
            notes="Allylamine-class target (terbinafine).",
        ),
    ],
    TargetPathogen.aspergillus_fumigatus: [
        TargetProtein(
            name="CYP51A",
            pdb_id="4UYL",
            uniprot_id="Q4WNT5",
            notes="Azole-class target.",
        ),
        TargetProtein(
            name="beta-1,3-glucan synthase (Fks1)",
            uniprot_id="Q9HEK5",
            notes="Echinocandin-class target.",
        ),
    ],
    TargetPathogen.cryptococcus_neoformans: [
        TargetProtein(
            name="ERG11 (CYP51 ortholog)",
            uniprot_id="P54264",
            notes="Azole-class target.",
        ),
    ],
}


def default_targets_for(pathogen: TargetPathogen) -> list[TargetProtein]:
    return list(ANTIFUNGAL_TARGET_PACK[pathogen])
