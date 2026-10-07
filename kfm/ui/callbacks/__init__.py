from . import chrome, pathway_map, wizard


def register_callbacks(app):
    chrome.register(app)
    wizard.register(app)
    pathway_map.register(app)
