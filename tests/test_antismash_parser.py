import json
from pathlib import Path

from hyphae.tools.antismash import parse_antismash_json


def test_parse_antismash_json_minimal(tmp_path: Path) -> None:
    payload = {
        "records": [
            {
                "id": "ctg1",
                "name": "ctg1",
                "length": 100_000,
                "features": [
                    {
                        "type": "region",
                        "location": "[10:1000](+)",
                        "qualifiers": {"product": ["T1PKS"]},
                    },
                    {
                        "type": "region",
                        "location": "[99000:100000](+)",
                        "qualifiers": {"product": ["NRPS"]},
                    },
                    {
                        "type": "CDS",
                        "location": "[10:200](+)",
                        "qualifiers": {},
                    },
                ],
            }
        ]
    }
    p = tmp_path / "as.json"
    p.write_text(json.dumps(payload))
    parsed = parse_antismash_json(p)
    assert len(parsed) == 2
    products = [r["product"] for r in parsed]
    assert "T1PKS" in products and "NRPS" in products
    # Edge truncation flagged for the region at the end of the contig.
    edge = next(r for r in parsed if r["product"] == "NRPS")
    assert edge["edge_truncated"] is True
