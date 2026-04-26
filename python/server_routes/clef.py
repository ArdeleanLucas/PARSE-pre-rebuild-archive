"""PARSE server route-domain module: clef."""
from __future__ import annotations

import server as _server

def _compute_contact_lexemes(job_id: str, payload: _server.Dict[str, _server.Any]) -> _server.Dict[str, _server.Any]:
    """Fetch and merge contact language lexeme forms into sil_contact_languages.json."""
    from compare.contact_lexeme_fetcher import fetch_and_merge
    concepts_path = _server._project_root() / 'concepts.csv'
    config_path = _server._sil_config_path()
    providers = _server._coerce_string_list(payload.get('providers')) or None
    languages_raw = _server._coerce_string_list(payload.get('languages'))
    if not languages_raw:
        sil_config = _server._load_sil_config_safe(config_path)
        meta = sil_config.get('_meta') if isinstance(sil_config.get('_meta'), dict) else {}
        primary = meta.get('primary_contact_languages') if isinstance(meta, dict) else None
        if isinstance(primary, list) and primary:
            languages_raw = [str(c).strip().lower() for c in primary if isinstance(c, str) and c.strip()]
        if not languages_raw:
            languages_raw = [k for k, v in sil_config.items() if isinstance(v, dict) and 'name' in v and isinstance(k, str) and (not k.startswith('_'))]
    overwrite = bool(payload.get('overwrite', False))

    def _progress(pct: float, msg: str) -> None:
        _server._set_job_progress(job_id, pct * 0.9, message=msg)
    try:
        ai_config_path = _server._project_root() / 'config' / 'ai_config.json'
        import json as _json2
        with open(ai_config_path) as f:
            ai_config = _json2.load(f)
    except Exception:
        ai_config = {}
    _server._set_job_progress(job_id, 5.0, message='Starting contact lexeme fetch')
    filled = fetch_and_merge(concepts_path=concepts_path, config_path=config_path, language_codes=languages_raw, providers=providers, overwrite=overwrite, ai_config=ai_config, progress_callback=_progress)
    _server._set_job_progress(job_id, 100.0, message='Done')
    total_filled = sum(filled.values())
    result: _server.Dict[str, _server.Any] = {'filled': filled, 'total_filled': total_filled, 'languages_requested': list(languages_raw), 'providers_requested': providers or 'all', 'config_path': str(config_path)}
    if total_filled == 0:
        result['warning'] = 'Populate finished with 0 reference forms. Try 1: check your internet connection — wikidata, wiktionary, asjp, cldf, and grokipedia all need network. Try 2: open the CLEF configure modal and enable more providers (or leave the list empty to try all built-in providers). Other causes: grokipedia needs an xAI API key; lingpy_wordlist and pycldf need local CLDF datasets under config/lexibank_data/; ASJP only covers 40 Swadesh concepts, so glosses outside that list return nothing from it. Backend stderr has per-provider errors.'
        print('[clef] {0}'.format(result['warning']), file=_server.sys.stderr)
    return result

def _api_get_contact_lexeme_coverage(self) -> None:
    """Return coverage stats for contact language lexeme data."""
    config_path = _server._sil_config_path()
    config = _server._load_sil_config_safe(config_path)
    concepts_path = _server._project_root() / 'concepts.csv'
    try:
        import csv as _csv
        with open(concepts_path, newline='') as f:
            reader = _csv.DictReader(f)
            all_concepts = [row.get('concept_en', '').strip() for row in reader if row.get('concept_en')]
    except (OSError, KeyError):
        all_concepts = []
    languages = {}
    for lang_code, lang_data in config.items():
        if not isinstance(lang_code, str) or lang_code.startswith('_'):
            continue
        if not isinstance(lang_data, dict) or 'name' not in lang_data:
            continue
        concepts_dict = lang_data.get('concepts', {})
        filled = {c: v for c, v in concepts_dict.items() if v}
        empty = [c for c in all_concepts if not filled.get(c)]
        languages[lang_code] = {'name': lang_data.get('name', lang_code), 'total': len(all_concepts), 'filled': len(filled), 'empty': len(empty), 'concepts': filled}
    self._send_json(_server.HTTPStatus.OK, {'languages': languages})

def _api_get_clef_config(self) -> None:
    """Return the current CLEF configuration + readiness state. The UI's
    configure modal reads this to decide whether to prompt the user
    before running Borrowing detection."""
    config_path = _server._sil_config_path()
    config = _server._load_sil_config_safe(config_path)
    meta_raw = config.get('_meta') if isinstance(config.get('_meta'), dict) else {}
    primary_raw = meta_raw.get('primary_contact_languages') if isinstance(meta_raw, dict) else []
    primary: _server.List[str] = []
    if isinstance(primary_raw, list):
        primary = [str(c).strip().lower() for c in primary_raw if isinstance(c, str) and c.strip()]
    languages = []
    for code, data in config.items():
        if not isinstance(code, str) or code.startswith('_'):
            continue
        if not isinstance(data, dict):
            continue
        concepts_dict = data.get('concepts', {}) if isinstance(data.get('concepts'), dict) else {}
        languages.append({'code': code, 'name': data.get('name') or code, 'family': data.get('family') or None, 'script': data.get('script') or None, 'filled': sum((1 for v in concepts_dict.values() if v)), 'total': len(concepts_dict)})
    languages.sort(key=lambda x: x['code'])
    configured = bool(primary) and len(languages) > 0
    concepts_exists = (_server._project_root() / 'concepts.csv').exists()
    self._send_json(_server.HTTPStatus.OK, {'configured': configured, 'primary_contact_languages': primary, 'languages': languages, 'config_path': str(config_path), 'concepts_csv_exists': concepts_exists, 'meta': meta_raw if isinstance(meta_raw, dict) else {}})

def _api_post_clef_config(self) -> None:
    """Create/update the SIL contact-language config. Accepts:
        {
          "primary_contact_languages": ["eng", "spa"],
          "languages": [
            {"code": "eng", "name": "English", "family": "Germanic"},
            ...
          ]
        }
    Merges with any existing per-language concepts data -- populated
    forms are never dropped when the user re-saves the config."""
    body = self._expect_object(self._read_json_body(), 'Request body')
    primary_raw = body.get('primary_contact_languages', [])
    if not isinstance(primary_raw, list):
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, 'primary_contact_languages must be a list')
    primary = [str(c).strip().lower() for c in primary_raw if isinstance(c, str) and c.strip()]
    if len(primary) > 2:
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, 'Pick at most 2 primary contact languages')
    langs_raw = body.get('languages', [])
    if not isinstance(langs_raw, list):
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, 'languages must be a list')
    clean_langs: _server.Dict[str, _server.Dict[str, _server.Any]] = {}
    for item in langs_raw:
        if not isinstance(item, dict):
            continue
        code = str(item.get('code', '')).strip().lower()
        if not code or code.startswith('_'):
            continue
        entry: _server.Dict[str, _server.Any] = {'name': str(item.get('name') or code)}
        family = item.get('family')
        if isinstance(family, str) and family.strip():
            entry['family'] = family.strip()
        script = item.get('script')
        if isinstance(script, str) and script.strip():
            entry['script'] = script.strip()
        clean_langs[code] = entry
    for code in primary:
        clean_langs.setdefault(code, {'name': code})
    config_path = _server._sil_config_path()
    existing = _server._load_sil_config_safe(config_path)
    merged: _server.Dict[str, _server.Any] = {}
    for code, entry in clean_langs.items():
        prev = existing.get(code) if isinstance(existing.get(code), dict) else {}
        prev_concepts = prev.get('concepts') if isinstance(prev.get('concepts'), dict) else {}
        merged[code] = {**entry, 'concepts': prev_concepts}
    prev_meta = existing.get('_meta') if isinstance(existing.get('_meta'), dict) else {}
    prev_selections = prev_meta.get('form_selections') if isinstance(prev_meta.get('form_selections'), dict) else None
    new_meta: _server.Dict[str, _server.Any] = {'primary_contact_languages': primary, 'configured_at': _server.datetime.now(_server.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z'), 'schema_version': 1}
    if prev_selections is not None:
        new_meta['form_selections'] = prev_selections
    merged['_meta'] = new_meta
    _server._write_sil_config(config_path, merged)
    self._send_json(_server.HTTPStatus.OK, {'success': True, 'config_path': str(config_path), 'primary_contact_languages': primary, 'language_count': len(clean_langs)})

def _api_post_clef_form_selections(self) -> None:
    """Persist which reference forms the user has selected for a given
    (concept, language) into ``_meta.form_selections`` in the SIL
    contact-language config.

    Request body:
        {
          "concept_en": "water",
          "lang_code": "ar",
          "forms": ["ماء", "maːʔ"]
        }

    Semantics downstream (honoured by future compute work, not this PR):
        - missing entry        → all populated forms are used (default)
        - empty ``forms`` list → none selected, similarity skipped
        - subset               → only listed forms contribute

    Selections are keyed by exact form string so the persisted choice
    survives re-population that preserves the same raw text. Adding or
    removing a concept/language from the config does not touch
    selections -- they stay keyed by English concept label + ISO code.
    """
    body = self._expect_object(self._read_json_body(), 'Request body')
    concept_en = body.get('concept_en')
    if not isinstance(concept_en, str) or not concept_en.strip():
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, 'concept_en must be a non-empty string')
    concept_key = concept_en.strip()
    lang_code_raw = body.get('lang_code')
    if not isinstance(lang_code_raw, str) or not lang_code_raw.strip():
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, 'lang_code must be a non-empty string')
    lang_code = lang_code_raw.strip().lower()
    if lang_code.startswith('_'):
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, "lang_code must not start with '_'")
    forms_raw = body.get('forms', [])
    if not isinstance(forms_raw, list):
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, 'forms must be a list of strings')
    forms: _server.List[str] = []
    seen: set = set()
    for item in forms_raw:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        forms.append(text)
    config_path = _server._sil_config_path()
    existing = _server._load_sil_config_safe(config_path)
    meta = existing.get('_meta')
    if not isinstance(meta, dict):
        meta = {}
    selections = meta.get('form_selections')
    if not isinstance(selections, dict):
        selections = {}
    concept_entry = selections.get(concept_key)
    if not isinstance(concept_entry, dict):
        concept_entry = {}
    concept_entry[lang_code] = forms
    selections[concept_key] = concept_entry
    meta['form_selections'] = selections
    existing['_meta'] = meta
    _server._write_sil_config(config_path, existing)
    self._send_json(_server.HTTPStatus.OK, {'success': True, 'concept_en': concept_key, 'lang_code': lang_code, 'forms': forms})

def _api_get_clef_catalog(self) -> None:
    """Return the bundled SIL/ISO language catalog the configure modal
    uses for its searchable picker. Kept server-side so we can extend
    it without reshipping the frontend bundle.

    Merges a per-workspace override file at
    ``config/sil_catalog_extra.json`` on top of the bundled list, so
    users can add private entries without editing the repo. The extras
    file may be a bare list or ``{"languages": [...]}``; duplicate
    codes in the extras replace the bundled entry."""
    from compare.sil_catalog import SIL_CATALOG
    merged: _server.Dict[str, _server.Dict[str, _server.Any]] = {}
    for entry in SIL_CATALOG:
        code = str(entry.get('code', '')).strip().lower()
        if not code:
            continue
        merged[code] = {k: v for k, v in entry.items() if v is not None}
    extras_path = _server._project_root() / 'config' / 'sil_catalog_extra.json'
    if extras_path.exists():
        try:
            with open(extras_path, encoding='utf-8') as f:
                raw = _server.json.load(f)
        except (OSError, ValueError):
            raw = None
        if isinstance(raw, dict):
            raw = raw.get('languages', [])
        if isinstance(raw, list):
            for item in raw:
                if not isinstance(item, dict):
                    continue
                code = str(item.get('code', '')).strip().lower()
                if not code:
                    continue
                merged[code] = {'code': code, 'name': str(item.get('name') or code), **({'family': item['family']} if isinstance(item.get('family'), str) and item['family'].strip() else {}), **({'script': item['script']} if isinstance(item.get('script'), str) and item['script'].strip() else {})}
    languages = sorted(merged.values(), key=lambda x: x.get('name', x.get('code', '')))
    self._send_json(_server.HTTPStatus.OK, {'languages': languages})

def _api_get_clef_providers(self) -> None:
    """Return the list of CLEF providers in priority order -- drives
    the provider-selection checkboxes in the configure modal."""
    from compare.providers.registry import PROVIDER_PRIORITY
    providers = [{'id': p, 'name': p} for p in PROVIDER_PRIORITY]
    self._send_json(_server.HTTPStatus.OK, {'providers': providers})

def _api_get_clef_sources_report(self) -> None:
    """Walk the SIL contact-language config and return a provenance
    report for academic citation. Accepts both the legacy bare-list
    and the new provenance shape, so the report is well-defined on
    partially-migrated corpora.

    Response shape::

        {
          "generated_at": "2026-04-25T...Z",
          "providers": [
            {"id": "wikidata", "total_forms": 42},
            {"id": "unknown", "total_forms": 7},   # legacy entries
            ...
          ],
          "languages": [
            {
              "code": "ar",
              "name": "Arabic",
              "total_forms": 25,
              "concepts_covered": 18,
              "concepts_total": 30,
              "per_provider": {"wikidata": 10, "asjp": 8, "unknown": 7},
              "forms": [
                {
                  "concept_en": "water",
                  "form": "ma:ʔ",
                  "sources": ["wikidata", "wiktionary"]
                },
                ...
              ]
            }
          ]
        }
    """
    from compare.providers.provenance import iter_forms_with_sources
    config_path = _server._sil_config_path()
    config = _server._load_sil_config_safe(config_path)
    concepts_path = _server._project_root() / 'concepts.csv'
    all_concepts_total = 0
    try:
        import csv as _csv
        with open(concepts_path, newline='') as f:
            reader = _csv.DictReader(f)
            all_concepts_total = sum((1 for row in reader if (row.get('concept_en') or '').strip()))
    except OSError:
        all_concepts_total = 0
    provider_totals: _server.Dict[str, int] = {}
    languages_out: _server.List[_server.Dict[str, _server.Any]] = []
    for code, data in sorted(config.items()):
        if not isinstance(code, str) or code.startswith('_'):
            continue
        if not isinstance(data, dict):
            continue
        concepts_dict = data.get('concepts') if isinstance(data.get('concepts'), dict) else {}
        forms_out: _server.List[_server.Dict[str, _server.Any]] = []
        per_provider: _server.Dict[str, int] = {}
        concepts_covered = 0
        for concept_en, entry in sorted(concepts_dict.items()):
            any_forms = False
            for form, sources in iter_forms_with_sources(entry):
                any_forms = True
                forms_out.append({'concept_en': concept_en, 'form': form, 'sources': list(sources)})
                for src in sources:
                    per_provider[src] = per_provider.get(src, 0) + 1
                    provider_totals[src] = provider_totals.get(src, 0) + 1
            if any_forms:
                concepts_covered += 1
        languages_out.append({'code': code, 'name': data.get('name') or code, 'family': data.get('family') or None, 'script': data.get('script') or None, 'total_forms': len(forms_out), 'concepts_covered': concepts_covered, 'concepts_total': all_concepts_total, 'per_provider': per_provider, 'forms': forms_out})
    providers_sorted = sorted(({'id': pid, 'total_forms': count} for pid, count in provider_totals.items()), key=lambda x: (-x['total_forms'], x['id']))
    from compare.providers.citations import get_citations, CITATION_DISPLAY_ORDER
    self._send_json(_server.HTTPStatus.OK, {'generated_at': _server.datetime.now(_server.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z'), 'providers': providers_sorted, 'languages': languages_out, 'concepts_total': all_concepts_total, 'citations': get_citations(), 'citation_order': list(CITATION_DISPLAY_ORDER)})

__all__ = ['_compute_contact_lexemes', '_api_get_contact_lexeme_coverage', '_api_get_clef_config', '_api_post_clef_config', '_api_post_clef_form_selections', '_api_get_clef_catalog', '_api_get_clef_providers', '_api_get_clef_sources_report']

