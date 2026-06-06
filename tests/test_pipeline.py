from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pipeline import conservative_valuation, process_candidates, run_gates


def test_conservative_valuation_calculates_bid_cap():
    item = {
        "estimated_sale_price": 80_000_000,
        "expected_resale_price": 120_000_000,
        "repair_cost": 5_000_000,
        "acquisition_cost": 3_000_000,
        "other_cost": 2_000_000,
    }

    result = conservative_valuation(item)

    assert result["total_cost"] == 90_000_000
    assert result["expected_margin"] == 30_000_000
    assert result["max_bid"] == 97_142_857


def test_hard_reject_stops_candidate():
    rules = {
        "gates": [
            {
                "type": "hard_reject",
                "rules": [
                    {
                        "field": "rights_clear",
                        "operator": "==",
                        "value": True,
                        "reason_code": "RIGHTS_UNCLEAR",
                    }
                ],
            }
        ]
    }

    status, reasons = run_gates(rules, {"rights_clear": False})

    assert status == "REJECT"
    assert reasons == ["RIGHTS_UNCLEAR"]


def test_process_candidates_returns_approved_result():
    candidate = {
        "candidate_id": "SAMPLE-1",
        "estimated_sale_price": 80_000_000,
        "expected_resale_price": 120_000_000,
        "repair_cost": 5_000_000,
        "acquisition_cost": 3_000_000,
        "other_cost": 2_000_000,
        "rights_clear": True,
    }
    rules = {
        "gates": [
            {
                "type": "hard_reject",
                "rules": [
                    {
                        "field": "rights_clear",
                        "operator": "==",
                        "value": True,
                        "reason_code": "RIGHTS_UNCLEAR",
                    }
                ],
            }
        ]
    }

    results = process_candidates([candidate], rules)

    assert len(results) == 1
    assert results[0].status == "APPROVED"
