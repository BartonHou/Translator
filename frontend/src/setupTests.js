import "@testing-library/jest-dom";

// Basic fetch mock to support component tests.
if (!global.fetch) {
  global.fetch = async () => ({
    ok: true,
    json: async () => ({
      registry: {
        "en->es": "Helsinki-NLP/opus-mt-en-es",
        "es->en": "Helsinki-NLP/opus-mt-es-en",
        "en->de": "Helsinki-NLP/opus-mt-en-de",
        "de->en": "Helsinki-NLP/opus-mt-de-en",
        "en->it": "Helsinki-NLP/opus-mt-en-it",
        "it->en": "Helsinki-NLP/opus-mt-it-en",
        "en->pt": "Helsinki-NLP/opus-mt-en-pt",
        "pt->en": "Helsinki-NLP/opus-mt-pt-en",
        "en->ja": "Helsinki-NLP/opus-mt-en-jap",
        "ja->en": "Helsinki-NLP/opus-mt-jap-en",
        "en->ko": "Helsinki-NLP/opus-mt-en-ko",
        "ko->en": "Helsinki-NLP/opus-mt-ko-en",
        "en->fr": "Helsinki-NLP/opus-mt-en-fr",
        "fr->en": "Helsinki-NLP/opus-mt-fr-en",
        "en->zh": "Helsinki-NLP/opus-mt-en-zh",
        "zh->en": "Helsinki-NLP/opus-mt-zh-en"
      }
    }),
    text: async () => ""
  });
}
