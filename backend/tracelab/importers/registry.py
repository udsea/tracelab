from tracelab.importers.atif import ATIFImporter
from tracelab.importers.atof import ATOFImporter
from tracelab.importers.generic import GenericStructuredImporter
from tracelab.importers.otel import OpenTelemetryImporter
from tracelab.importers.sessions import HFSessionTraceImporter
from tracelab.inspect_adapter.importer import InspectImporter

IMPORTERS = [
    InspectImporter(),
    ATIFImporter(),
    ATOFImporter(),
    HFSessionTraceImporter(),
    OpenTelemetryImporter(),
    GenericStructuredImporter(),
]


def detect(source, ref):
    results = [importer.detect(source, ref) for importer in IMPORTERS]
    return sorted(results, key=lambda result: result.confidence, reverse=True)


def get_importer(name):
    return next(importer for importer in IMPORTERS if importer.name == name)


def choose(source, ref):
    results = detect(source, ref)
    if not results or (results[0].confidence < 0.5 and results[0].format != "generic"):
        raise ValueError("No supported trajectory structure detected")
    return get_importer(results[0].format), results
