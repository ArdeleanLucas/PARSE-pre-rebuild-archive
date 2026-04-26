"""PARSE server route-domain module: compare."""
from __future__ import annotations

import server as _server

def _compute_cognates(job_id: str, payload: _server.Dict[str, _server.Any]) -> _server.Dict[str, _server.Any]:
    if _server.cognate_compute_module is None:
        raise RuntimeError('compare.cognate_compute is unavailable')
    threshold_raw = payload.get('threshold', 0.6)
    try:
        threshold = float(threshold_raw)
    except (TypeError, ValueError):
        raise RuntimeError('threshold must be a number')
    if threshold <= 0.0:
        raise RuntimeError('threshold must be greater than 0')
    speaker_filter_values = _server._coerce_string_list(payload.get('speakers'))
    speaker_filter = set(speaker_filter_values)
    concept_filter_values = _server._coerce_concept_id_list(payload.get('conceptIds'))
    concept_filter = set(concept_filter_values)
    contact_override = [code.lower() for code in _server._coerce_string_list(payload.get('contactLanguages'))]
    if not contact_override:
        contact_override = [code.lower() for code in _server._coerce_string_list(payload.get('contact_languages'))]
    annotations_dir_raw = payload.get('annotationsDir', payload.get('annotations_dir', 'annotations'))
    annotations_dir = _server._resolve_project_path(str(annotations_dir_raw))
    _server._set_job_progress(job_id, 10.0, message='Loading contact language data')
    contact_languages_from_config, refs_by_concept, form_selections_by_concept = _server.cognate_compute_module.load_contact_language_data(_server._sil_config_path())
    contact_languages = contact_override or contact_languages_from_config
    _server._set_job_progress(job_id, 25.0, message='Loading annotation files')
    forms_by_concept, discovered_speakers = _server.cognate_compute_module.load_annotations(annotations_dir)
    filtered_forms: _server.Dict[str, _server.List[_server.Any]] = {}
    for concept_id, records in forms_by_concept.items():
        normalized_concept_id = _server._normalize_concept_id(concept_id)
        if concept_filter and normalized_concept_id not in concept_filter:
            continue
        kept_records: _server.List[_server.Any] = []
        for record in records:
            record_speaker = str(getattr(record, 'speaker', '')).strip()
            if speaker_filter and record_speaker not in speaker_filter:
                continue
            kept_records.append(record)
        if kept_records:
            filtered_forms[normalized_concept_id] = kept_records
    if concept_filter_values:
        selected_concept_ids = concept_filter_values
    else:
        selected_concept_ids = sorted(filtered_forms.keys(), key=_server._concept_sort_key)
    concept_specs = [_server.cognate_compute_module.ConceptSpec(concept_id=concept_id, label='') for concept_id in selected_concept_ids]
    _server._set_job_progress(job_id, 45.0, message='Computing cognate sets')
    cognate_sets = _server.cognate_compute_module._compute_cognate_sets_with_lingpy(filtered_forms, concept_specs, threshold)
    _server._set_job_progress(job_id, 75.0, message='Computing similarity scores')
    similarity = _server.cognate_compute_module.compute_similarity_scores(forms_by_concept=filtered_forms, concepts=concept_specs, contact_languages=contact_languages, refs_by_concept=refs_by_concept, form_selections_by_concept=form_selections_by_concept)
    if speaker_filter_values:
        speakers_included = sorted([speaker for speaker in discovered_speakers if speaker in speaker_filter])
    else:
        speakers_included = sorted(discovered_speakers)
    enrichments_payload = {'computed_at': _server._utc_now_iso(), 'config': {'contact_languages': list(contact_languages), 'speakers_included': speakers_included, 'concepts_included': [_server._concept_out_value(concept_id) for concept_id in selected_concept_ids], 'lexstat_threshold': round(float(threshold), 3)}, 'cognate_sets': cognate_sets, 'similarity': similarity, 'borrowing_flags': {}, 'manual_overrides': {}}
    _server._set_job_progress(job_id, 92.0, message='Writing parse-enrichments.json')
    output_path = _server._enrichments_path()
    _server._write_json_file(output_path, enrichments_payload)
    return {'type': 'cognates', 'outputPath': str(output_path), 'computedAt': enrichments_payload['computed_at'], 'conceptCount': len(enrichments_payload['config']['concepts_included']), 'speakerCount': len(enrichments_payload['config']['speakers_included'])}

def _api_get_enrichments(self) -> None:
    payload = _server._read_json_file(_server._enrichments_path(), _server._default_enrichments_payload())
    self._send_json(_server.HTTPStatus.OK, {'enrichments': payload})

def _api_post_enrichments(self) -> None:
    body = self._read_json_body(required=True)
    if not isinstance(body, dict):
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, 'Enrichments payload must be a JSON object')
    enrichments_payload = body.get('enrichments') if isinstance(body.get('enrichments'), dict) else body
    _server._write_json_file(_server._enrichments_path(), enrichments_payload)
    self._send_json(_server.HTTPStatus.OK, {'success': True})

def _api_post_lexeme_note(self) -> None:
    """Write a single lexeme-level note into parse-enrichments.json."""
    body = self._expect_object(self._read_json_body(required=True), 'Request body')
    speaker_raw = str(body.get('speaker') or '').strip()
    concept_id = _server._normalize_concept_id(body.get('concept_id'))
    if not speaker_raw or not concept_id:
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, 'speaker and concept_id are required')
    try:
        speaker = _server._normalize_speaker_id(speaker_raw)
    except ValueError as exc:
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, str(exc))
    payload = _server._read_json_file(_server._enrichments_path(), _server._default_enrichments_payload())
    notes_block = payload.get('lexeme_notes')
    if not isinstance(notes_block, dict):
        notes_block = {}
        payload['lexeme_notes'] = notes_block
    speaker_block = notes_block.get(speaker)
    if not isinstance(speaker_block, dict):
        speaker_block = {}
        notes_block[speaker] = speaker_block
    if body.get('delete') is True:
        speaker_block.pop(concept_id, None)
        if not speaker_block:
            notes_block.pop(speaker, None)
    else:
        entry = speaker_block.get(concept_id)
        if not isinstance(entry, dict):
            entry = {}
        if 'user_note' in body:
            entry['user_note'] = str(body.get('user_note') or '')
        if 'import_note' in body:
            entry['import_note'] = str(body.get('import_note') or '')
        entry['updated_at'] = _server._utc_now_iso()
        speaker_block[concept_id] = entry
    _server._write_json_file(_server._enrichments_path(), payload)
    self._send_json(_server.HTTPStatus.OK, {'success': True, 'lexeme_notes': payload.get('lexeme_notes') or {}})

def _api_post_lexeme_notes_import(self) -> None:
    """Multipart POST — parse Audition comments CSV into lexeme_notes."""
    from lexeme_notes import parse_audition_csv, match_rows_to_lexemes
    content_type = self.headers.get('Content-Type', '')
    if 'multipart/form-data' not in content_type:
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, 'Content-Type must be multipart/form-data')
    raw_length = self.headers.get('Content-Length', '')
    try:
        content_length = int(raw_length)
    except (ValueError, TypeError):
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, 'Content-Length header is required')
    if content_length > _server.ONBOARD_MAX_UPLOAD_BYTES:
        raise _server.ApiError(_server.HTTPStatus.REQUEST_ENTITY_TOO_LARGE, 'Upload exceeds limit')
    environ = {'REQUEST_METHOD': 'POST', 'CONTENT_TYPE': content_type, 'CONTENT_LENGTH': str(content_length)}
    form = _server.cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ=environ, keep_blank_values=True)
    speaker_field = form.getfirst('speaker_id', '') if 'speaker_id' in form else ''
    if isinstance(speaker_field, bytes):
        speaker_field = speaker_field.decode('utf-8', errors='replace')
    try:
        speaker = _server._normalize_speaker_id(str(speaker_field or '').strip())
    except ValueError as exc:
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, str(exc))
    csv_item = form['csv'] if 'csv' in form else None
    if csv_item is None or not getattr(csv_item, 'filename', None):
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, 'csv file is required (field name: csv)')
    try:
        csv_text = csv_item.file.read().decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, 'csv must be UTF-8: {0}'.format(exc))
    rows = parse_audition_csv(csv_text)
    if not rows:
        self._send_json(_server.HTTPStatus.OK, {'success': True, 'imported': 0, 'matched': 0, 'total_rows': 0})
        return
    annotation_path = _server._annotation_read_path_for_speaker(speaker)
    annotation_payload = _server._read_json_any_file(annotation_path)
    normalized = _server._normalize_annotation_record(annotation_payload, speaker)
    tiers = normalized.get('tiers') or {}
    concept_tier = tiers.get('concept') if isinstance(tiers, dict) else None
    intervals: _server.List[_server.Dict[str, _server.Any]] = []
    if isinstance(concept_tier, dict):
        for iv in concept_tier.get('intervals') or []:
            if not isinstance(iv, dict):
                continue
            cid = _server._normalize_concept_id(iv.get('text'))
            if not cid:
                continue
            try:
                start = float(iv.get('start') or 0.0)
                end = float(iv.get('end') or 0.0)
            except (TypeError, ValueError):
                continue
            intervals.append({'concept_id': cid, 'start': start, 'end': end})
    concept_labels: _server.Dict[str, str] = {}
    survey_to_id: _server.Dict[str, str] = {}
    try:
        import csv as _csv
        concepts_path = _server._project_root() / 'concepts.csv'
        if concepts_path.exists():
            with open(concepts_path, newline='', encoding='utf-8') as fh:
                for row in _csv.DictReader(fh):
                    cid = _server._normalize_concept_id(row.get('id'))
                    label = str(row.get('concept_en') or '').strip()
                    survey = str(row.get('survey_item') or '').strip()
                    if cid and label:
                        concept_labels[cid] = label
                    if cid and survey:
                        m = _server.re.match('^[A-Za-z]+_([0-9]+(?:\\.[0-9]+)?)', survey)
                        if m:
                            key = m.group(1)
                            survey_to_id.setdefault(key, cid)
                            concept_labels.setdefault(key, label)
    except Exception:
        concept_labels = {}
        survey_to_id = {}
    matches = match_rows_to_lexemes(rows, intervals, concept_labels=concept_labels)
    label_to_id = {lbl.lower(): cid for cid, lbl in concept_labels.items() if cid.isdigit()}
    for row, match in zip(rows, matches):
        csv_id = _server._normalize_concept_id(row.concept_id)
        if csv_id in survey_to_id:
            match['concept_id'] = survey_to_id[csv_id]
            continue
        current = _server._normalize_concept_id(match.get('concept_id'))
        if current.isdigit():
            continue
        if current.lower() in label_to_id:
            match['concept_id'] = label_to_id[current.lower()]
    payload = _server._read_json_file(_server._enrichments_path(), _server._default_enrichments_payload())
    notes_block = payload.get('lexeme_notes')
    if not isinstance(notes_block, dict):
        notes_block = {}
        payload['lexeme_notes'] = notes_block
    speaker_block = notes_block.get(speaker)
    if not isinstance(speaker_block, dict):
        speaker_block = {}
        notes_block[speaker] = speaker_block
    imported = 0
    for match in matches:
        note_text = str(match.get('note') or '').strip()
        if not note_text:
            continue
        cid = _server._normalize_concept_id(match.get('concept_id'))
        if not cid:
            continue
        entry = speaker_block.get(cid)
        if not isinstance(entry, dict):
            entry = {}
        entry['import_note'] = note_text
        entry['import_raw'] = str(match.get('raw_name') or '')
        entry['updated_at'] = _server._utc_now_iso()
        speaker_block[cid] = entry
        imported += 1
    _server._write_json_file(_server._enrichments_path(), payload)
    self._send_json(_server.HTTPStatus.OK, {'success': True, 'speaker': speaker, 'total_rows': len(rows), 'imported': imported, 'matched': sum((1 for m in matches if m.get('was_matched'))), 'lexeme_notes': payload.get('lexeme_notes') or {}})

def _api_get_lexeme_search(self) -> None:
    """GET /api/lexeme/search — rank candidate time ranges for a concept.

    Query params:
        speaker       — required, the target speaker
        variants      — required, comma/space-separated orthographic forms
        concept_id    — optional, enables the cross-speaker signal + auto
                        augmentation with contact-lexeme variants
        language      — optional, phonemizer language code (default "ku")
        tiers         — optional, comma-separated subset of
                        ortho_words,ortho,stt,ipa (default all)
        limit         — optional, max candidates to return (default 10)
        max_distance  — optional float in (0, 1] — normalized Levenshtein
                        threshold, anything worse is dropped (default 0.55)

    Response JSON:
        {
          speaker, concept_id, variants, language,
          candidates: [{ start, end, tier, matched_text, matched_variant,
                         score, phonetic_score, cross_speaker_score,
                         confidence_weight, source_label }],
          signals_available: {
             phonemizer: bool, cross_speaker_anchors: int,
             contact_variants: [str]
          }
        }
    """
    try:
        from ai import lexeme_search as lex
    except Exception:
        try:
            from python.ai import lexeme_search as lex
        except Exception as exc:
            raise _server.ApiError(_server.HTTPStatus.INTERNAL_SERVER_ERROR, 'lexeme_search module unavailable: {0}'.format(exc))
    from urllib.parse import parse_qs
    query = _server.urlparse(self.path).query
    params = {k: v[0] for k, v in parse_qs(query).items() if v}
    speaker_raw = str(params.get('speaker') or '').strip()
    if not speaker_raw:
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, 'speaker is required')
    try:
        speaker = _server._normalize_speaker_id(speaker_raw)
    except ValueError as exc:
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, str(exc))
    variants_raw = str(params.get('variants') or '').strip()
    user_variants = [v for v in _server.re.split('[\\s,;/]+', variants_raw) if v]
    if not user_variants:
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, 'variants is required (comma or space separated)')
    concept_id = str(params.get('concept_id') or '').strip() or None
    language = str(params.get('language') or lex.DEFAULT_LANGUAGE).strip() or lex.DEFAULT_LANGUAGE
    tiers_raw = str(params.get('tiers') or '').strip()
    tiers_filter: _server.Optional[list] = None
    if tiers_raw:
        tiers_filter = [t for t in _server.re.split('[\\s,;]+', tiers_raw) if t]
    try:
        limit = int(params.get('limit') or lex.DEFAULT_LIMIT)
    except (TypeError, ValueError):
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, 'limit must be an integer')
    if limit <= 0 or limit > 200:
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, 'limit must be in [1, 200]')
    try:
        max_distance = float(params.get('max_distance') or lex.DEFAULT_MAX_DISTANCE)
    except (TypeError, ValueError):
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, 'max_distance must be a number in (0, 1]')
    if not 0 < max_distance <= 1:
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, 'max_distance must be in (0, 1]')
    try:
        target_path = _server._annotation_read_path_for_speaker(speaker)
    except ValueError as exc:
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, str(exc))
    if not target_path.is_file():
        raise _server.ApiError(_server.HTTPStatus.NOT_FOUND, 'No annotation record for speaker {0}'.format(speaker))
    target_raw = _server._read_json_any_file(target_path)
    target_record = _server._normalize_annotation_record(target_raw, speaker)
    cross_records: list = []
    if concept_id:
        annotations_dir = _server._project_root() / 'annotations'
        if annotations_dir.is_dir():
            for path in sorted(annotations_dir.iterdir()):
                if not path.is_file():
                    continue
                if path.suffix not in {'.json'}:
                    continue
                stem = path.name.removesuffix(_server.ANNOTATION_FILENAME_SUFFIX).removesuffix(_server.ANNOTATION_LEGACY_FILENAME_SUFFIX)
                if stem == speaker:
                    continue
                try:
                    raw = _server._read_json_any_file(path)
                    cross_records.append(_server._normalize_annotation_record(raw, stem))
                except Exception:
                    continue
    contact_variants: list = []
    if concept_id:
        try:
            contact_variants = lex.load_contact_variants(concept_id, _server._sil_config_path())
        except Exception:
            contact_variants = []
    all_variants = list(user_variants)
    seen = {v for v in all_variants}
    for v in contact_variants:
        if v not in seen:
            all_variants.append(v)
            seen.add(v)
    candidates = lex.search(target_record, all_variants, concept_id=concept_id, cross_speaker_records=cross_records, language=language, limit=limit, max_distance=max_distance, tiers=tiers_filter)
    phonemizer_available = bool(lex.phonemize_variant(user_variants[0], language=language))
    self._send_json(_server.HTTPStatus.OK, {'speaker': speaker, 'concept_id': concept_id, 'variants': user_variants, 'language': language, 'candidates': candidates, 'signals_available': {'phonemizer': phonemizer_available, 'cross_speaker_anchors': sum((1 for rec in cross_records if concept_id and str(concept_id) in ((rec or {}).get('confirmed_anchors') or {}))), 'contact_variants': contact_variants}})

def _api_get_tags(self) -> None:
    """GET /api/tags — return parse-tags.json as tag array."""
    tags_path = _server._project_root() / 'parse-tags.json'
    if not tags_path.exists():
        self._send_json(_server.HTTPStatus.OK, {'tags': []})
        return
    try:
        with open(tags_path, 'r', encoding='utf-8') as f:
            data = _server.json.load(f)
        if isinstance(data, list):
            self._send_json(_server.HTTPStatus.OK, {'tags': data})
        else:
            self._send_json(_server.HTTPStatus.OK, {'tags': []})
    except Exception as exc:
        self._send_json(_server.HTTPStatus.INTERNAL_SERVER_ERROR, {'error': str(exc)})

def _api_post_tags_merge(self) -> None:
    """POST /api/tags/merge — additive merge of incoming tags into parse-tags.json."""
    try:
        data = self._expect_object(self._read_json_body(required=True), 'Request body')
        incoming = data.get('tags')
        if not isinstance(incoming, list):
            self._send_json(_server.HTTPStatus.BAD_REQUEST, {'error': 'tags must be an array'})
            return
        tags_path = _server._project_root() / 'parse-tags.json'
        existing: list = []
        if tags_path.exists():
            try:
                with open(tags_path, 'r', encoding='utf-8') as f:
                    raw = _server.json.load(f)
                if isinstance(raw, list):
                    existing = raw
            except Exception:
                existing = []
        existing_by_id = {t['id']: t for t in existing if isinstance(t, dict) and 'id' in t}
        for tag in incoming:
            if not isinstance(tag, dict) or 'id' not in tag:
                continue
            tid = str(tag['id'])
            if tid in existing_by_id:
                prev = existing_by_id[tid]
                merged = set(prev.get('concepts') or [])
                merged.update(tag.get('concepts') or [])
                prev['concepts'] = sorted(merged)
                prev['label'] = tag.get('label', prev.get('label', ''))
                prev['color'] = tag.get('color', prev.get('color', '#6b7280'))
            else:
                existing_by_id[tid] = {'id': tid, 'label': str(tag.get('label') or ''), 'color': str(tag.get('color') or '#6b7280'), 'concepts': sorted(set(tag.get('concepts') or []))}
        merged_list = list(existing_by_id.values())
        with open(tags_path, 'w', encoding='utf-8') as f:
            _server.json.dump(merged_list, f, indent=2, ensure_ascii=False)
        self._send_json(_server.HTTPStatus.OK, {'ok': True, 'tagCount': len(merged_list)})
    except _server.ApiError:
        raise
    except Exception as exc:
        self._send_json(_server.HTTPStatus.INTERNAL_SERVER_ERROR, {'error': str(exc)})

__all__ = ['_compute_cognates', '_api_get_enrichments', '_api_post_enrichments', '_api_post_lexeme_note', '_api_post_lexeme_notes_import', '_api_get_lexeme_search', '_api_get_tags', '_api_post_tags_merge']

