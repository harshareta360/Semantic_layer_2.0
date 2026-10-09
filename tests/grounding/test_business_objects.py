from semantic_layer.grounding.business_objects import load_business_objects


def test_load_business_objects():
    reg = load_business_objects()
    assert reg is not None
    assert "Finance" in reg.business_objects
    assert "Logistics" in reg.business_objects
    fin = reg.require("Finance")
    assert "public_payment_details" in fin.table_names
    assert "public_logistics_orders" not in fin.table_names
    log = reg.require("Logistics")
    assert "public_logistics_orders" in log.table_names
    assert "public_payment_details" not in log.table_names


def test_unknown_bo_raises():
    reg = load_business_objects()
    assert reg is not None
    try:
        reg.require("Marketing")
        assert False, "expected KeyError"
    except KeyError as exc:
        assert "Marketing" in str(exc)
