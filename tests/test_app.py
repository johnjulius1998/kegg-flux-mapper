def test_app_builds_with_key_components():
    from app import create_app
    app = create_app()
    layout = repr(app.layout)
    for cid in ["config-modal", "pathway-list", "pathway-graph", "mode-seg",
                "reaction-offcanvas", "table-sheet", "store-key-a", "analyse-btn"]:
        assert f"'{cid}'" in layout, cid
    assert len(app.callback_map) >= 20
