from app.models.filter import FilterDefinition, FilterOption


def test_filter_definition_to_dict_excludes_inactive_options() -> None:
    definition = FilterDefinition(
        id="01HF4G12ABCDEF3456789XYZAB",
        key="goal",
        display_name="Goal",
        filter_type="multi_select",
    )
    definition.options = [
        FilterOption(
            id="01HF4G12ABCDEF3456789XYZAC",
            filter_definition_id=definition.id,
            value="enrichment",
            display_name="Enrichment",
            display_order=0,
            is_active=True,
        ),
        FilterOption(
            id="01HF4G12ABCDEF3456789XYZAD",
            filter_definition_id=definition.id,
            value="competition",
            display_name="Competition",
            display_order=1,
            is_active=False,
        ),
    ]

    payload = definition.to_dict(include_options=True)

    assert payload["filter_type"] == "multi_select"
    assert payload["options"] == [
        {
            "id": "01HF4G12ABCDEF3456789XYZAC",
            "value": "enrichment",
            "display_name": "Enrichment",
            "display_order": 0,
        }
    ]
