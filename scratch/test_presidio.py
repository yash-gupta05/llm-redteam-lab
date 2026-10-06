from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import NlpEngineProvider

# Tell Presidio to use the small spaCy model instead of its large default.
config = {
    "nlp_engine_name": "spacy",
    "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
}
nlp_engine = NlpEngineProvider(nlp_configuration=config).create_engine()
analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])

text = "My name is John Smith, my email is john@example.com and my phone is 212-555-0199."
for r in analyzer.analyze(text=text, language="en"):
    print(r.entity_type, "->", text[r.start:r.end], f"(confidence {r.score:.2f})")