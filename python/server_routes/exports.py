"""PARSE server route-domain module: exports."""
from __future__ import annotations

import server as _server

def _api_get_export_lingpy(self) -> None:
    """Stream LingPy-compatible wordlist TSV as a file download."""
    import tempfile
    tmp_fd, tmp_str = tempfile.mkstemp(suffix='.tsv')
    import os as _os
    _os.close(tmp_fd)
    tmp_path = _server.pathlib.Path(tmp_str)
    try:
        _server.cognate_compute_module.export_wordlist_tsv(_server._enrichments_path(), _server._project_root() / 'annotations', tmp_path)
        content = tmp_path.read_bytes()
    finally:
        try:
            _os.unlink(tmp_str)
        except OSError:
            pass
    self.send_response(_server.HTTPStatus.OK)
    self.send_header('Content-Type', 'text/tab-separated-values; charset=utf-8')
    self.send_header('Content-Disposition', 'attachment; filename="parse-wordlist.tsv"')
    self.send_header('Content-Length', str(len(content)))
    self.end_headers()
    self.wfile.write(content)

def _api_get_export_nexus(self) -> None:
    """Emit a NEXUS character matrix compatible with BEAST2.

    One character per (concept, cognate group). For each speaker:
      1  — speaker is in this cognate group for the concept
      0  — speaker has a form for the concept but sits in a different group
      ?  — speaker has no form / unreviewed for the concept
    Manual overrides in ``manual_overrides.cognate_sets`` take precedence
    over the auto-computed ``cognate_sets`` block.
    """
    enrichments = _server._read_json_file(_server._enrichments_path(), _server._default_enrichments_payload())
    overrides = enrichments.get('manual_overrides') or {}
    override_sets = overrides.get('cognate_sets') if isinstance(overrides, dict) else None
    auto_sets = enrichments.get('cognate_sets') if isinstance(enrichments, dict) else None
    override_sets = override_sets if isinstance(override_sets, dict) else {}
    auto_sets = auto_sets if isinstance(auto_sets, dict) else {}
    speakers_set: set = set()
    project_payload = _server._read_json_file(_server._project_json_path(), {})
    speakers_block = project_payload.get('speakers') if isinstance(project_payload, dict) else None
    if isinstance(speakers_block, dict):
        speakers_set.update((str(s) for s in speakers_block.keys() if str(s).strip()))
    elif isinstance(speakers_block, list):
        speakers_set.update((str(s) for s in speakers_block if str(s).strip()))
    concept_keys: _server.List[str] = []
    concept_group_members: _server.Dict[str, _server.Dict[str, _server.List[str]]] = {}
    union_keys: _server.List[str] = []
    seen_keys: set = set()
    for key in list(override_sets.keys()) + list(auto_sets.keys()):
        if key not in seen_keys:
            seen_keys.add(key)
            union_keys.append(key)
    for key in union_keys:
        override_block = override_sets.get(key)
        auto_block = auto_sets.get(key)
        block = override_block if isinstance(override_block, dict) else auto_block
        if not isinstance(block, dict):
            continue
        groups: _server.Dict[str, _server.List[str]] = {}
        for group, members in block.items():
            if not isinstance(members, list):
                continue
            cleaned = [str(m) for m in members if str(m).strip()]
            if cleaned:
                groups[str(group)] = cleaned
                speakers_set.update(cleaned)
        if groups:
            concept_group_members[key] = groups
            concept_keys.append(key)
    speakers = sorted(speakers_set)
    has_form: _server.Dict[str, set] = {}
    for key in concept_keys:
        present: set = set()
        for members in concept_group_members[key].values():
            present.update(members)
        has_form[key] = present
    characters: _server.List[_server.Tuple[str, str, str]] = []
    for key in sorted(concept_keys, key=_server._concept_sort_key):
        for group in sorted(concept_group_members[key].keys()):
            label = '{0}_{1}'.format(str(key).replace(' ', '_'), group)
            characters.append((key, group, label))

    def row_for(speaker: str) -> str:
        chars: _server.List[str] = []
        for key, group, _lbl in characters:
            members = concept_group_members[key].get(group, [])
            if speaker in members:
                chars.append('1')
            elif speaker in has_form.get(key, set()):
                chars.append('0')
            else:
                chars.append('?')
        return ''.join(chars)
    lines: _server.List[str] = []
    lines.append('#NEXUS')
    lines.append('')
    lines.append('BEGIN TAXA;')
    lines.append('    DIMENSIONS NTAX={0};'.format(len(speakers)))
    if speakers:
        lines.append('    TAXLABELS')
        for sp in speakers:
            lines.append('        {0}'.format(sp))
        lines.append('    ;')
    lines.append('END;')
    lines.append('')
    lines.append('BEGIN CHARACTERS;')
    lines.append('    DIMENSIONS NCHAR={0};'.format(len(characters)))
    lines.append('    FORMAT DATATYPE=STANDARD MISSING=? GAP=- SYMBOLS="01";')
    if characters:
        lines.append('    CHARSTATELABELS')
        label_rows = []
        for idx, (_key, _group, label) in enumerate(characters, start=1):
            label_rows.append('        {0} {1}'.format(idx, label))
        lines.append(',\n'.join(label_rows))
        lines.append('    ;')
    lines.append('    MATRIX')
    for sp in speakers:
        lines.append('        {0}    {1}'.format(sp, row_for(sp)))
    lines.append('    ;')
    lines.append('END;')
    lines.append('')
    nexus_text = '\n'.join(lines).encode('utf-8')
    self.send_response(_server.HTTPStatus.OK)
    self.send_header('Content-Type', 'text/plain; charset=utf-8')
    self.send_header('Content-Disposition', 'attachment; filename="parse-cognates.nex"')
    self.send_header('Content-Length', str(len(nexus_text)))
    self.end_headers()
    try:
        self.wfile.write(nexus_text)
    except BrokenPipeError:
        pass

def _api_post_concepts_import(self) -> None:
    """Merge survey_item / custom_order from an uploaded CSV into concepts.csv.

    Upload format (CSV with header):
        - `id` or `concept_en` (at least one for matching)
        - `survey_item` (optional string)
        - `custom_order` (optional integer; blank/non-numeric clears the field)

    Matching: `id` first, then case-insensitive `concept_en`.
    Rows in the existing concepts.csv that aren't in the upload keep their
    existing `survey_item` / `custom_order`. Pass `?mode=replace` to clear
    those fields on non-matching rows instead.
    """
    import csv as _csv
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
    csv_item = form['csv'] if 'csv' in form else None
    if csv_item is None or not getattr(csv_item, 'filename', None):
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, 'csv file is required (field name: csv)')
    try:
        csv_text = csv_item.file.read().decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, 'csv must be UTF-8: {0}'.format(exc))
    mode_field = form.getfirst('mode', '') if 'mode' in form else ''
    replace_mode = str(mode_field or '').strip().lower() == 'replace'
    try:
        reader = _csv.DictReader(_server.io.StringIO(csv_text))
        upload_rows = list(reader)
    except _csv.Error as exc:
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, 'csv parse error: {0}'.format(exc))
    if not upload_rows:
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, 'csv is empty')
    fieldnames = [str(n or '').strip().lower() for n in reader.fieldnames or []]
    if 'id' not in fieldnames and 'concept_en' not in fieldnames:
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, 'csv must have an id or concept_en column')
    concepts_path = _server._project_root() / 'concepts.csv'
    existing: _server.List[_server.Dict[str, str]] = []
    if concepts_path.exists():
        with open(concepts_path, newline='', encoding='utf-8') as f:
            existing = list(_csv.DictReader(f))
    by_id: _server.Dict[str, int] = {}
    by_label: _server.Dict[str, int] = {}
    for idx, row in enumerate(existing):
        rid = _server._normalize_concept_id(row.get('id'))
        lbl = str(row.get('concept_en') or '').strip().lower()
        if rid:
            by_id[rid] = idx
        if lbl:
            by_label[lbl] = idx
    if replace_mode:
        for row in existing:
            row['survey_item'] = ''
            row['custom_order'] = ''
    matched = 0
    added = 0
    for up in upload_rows:
        up_id = _server._normalize_concept_id(up.get('id'))
        up_label = str(up.get('concept_en') or '').strip()
        target_idx: _server.Optional[int] = None
        if up_id and up_id in by_id:
            target_idx = by_id[up_id]
        elif up_label and up_label.lower() in by_label:
            target_idx = by_label[up_label.lower()]
        survey_raw = str(up.get('survey_item') or '').strip() if 'survey_item' in up else ''
        custom_raw = str(up.get('custom_order') or '').strip() if 'custom_order' in up else ''
        if target_idx is None:
            if not up_label:
                continue
            if not up_id:
                existing_ids = {_server._normalize_concept_id(r.get('id')) for r in existing}
                next_id = 1
                while str(next_id) in existing_ids:
                    next_id += 1
                up_id = str(next_id)
            row = {'id': up_id, 'concept_en': up_label, 'survey_item': survey_raw, 'custom_order': custom_raw}
            existing.append(row)
            by_id[up_id] = len(existing) - 1
            by_label[up_label.lower()] = len(existing) - 1
            added += 1
        else:
            row = existing[target_idx]
            if survey_raw:
                row['survey_item'] = survey_raw
            if custom_raw:
                row['custom_order'] = custom_raw
            matched += 1
    fieldnames_out = ['id', 'concept_en', 'survey_item', 'custom_order']
    concepts_path.parent.mkdir(parents=True, exist_ok=True)
    with open(concepts_path, 'w', newline='', encoding='utf-8') as f:
        writer = _csv.DictWriter(f, fieldnames=fieldnames_out)
        writer.writeheader()
        for row in existing:
            writer.writerow({k: row.get(k, '') or '' for k in fieldnames_out})
    self._send_json(_server.HTTPStatus.OK, {'ok': True, 'matched': matched, 'added': added, 'total': len(existing), 'mode': 'replace' if replace_mode else 'merge'})

def _api_post_tags_import(self) -> None:
    """Import a custom concept list as a TAG with auto-assigned concepts.

    Multipart form fields:
        - `csv` (file, required): columns `id` and/or `concept_en`.
        - `tagName` (text, optional): defaults to the CSV filename stem.
        - `color` (text, optional): hex or named, default "#4461d4".

    Each CSV row is matched to an existing project concept by `id` first,
    else case-insensitive `concept_en`. Matched concept ids are added to
    the tag (merged — never removes existing assignments). Unmatched rows
    are reported as `missedLabels` so the caller can review.
    """
    import csv as _csv
    import re as _re
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
    csv_item = form['csv'] if 'csv' in form else None
    if csv_item is None or not getattr(csv_item, 'filename', None):
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, 'csv file is required (field name: csv)')
    try:
        csv_text = csv_item.file.read().decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, 'csv must be UTF-8: {0}'.format(exc))
    csv_filename = _server.os.path.basename(csv_item.filename or 'tag.csv')
    tag_name_field = form.getfirst('tagName', '') if 'tagName' in form else ''
    color_field = form.getfirst('color', '') if 'color' in form else ''
    tag_name = str(tag_name_field or '').strip()
    if not tag_name:
        tag_name = _server.pathlib.Path(csv_filename).stem or 'Custom list'
    color = str(color_field or '').strip() or '#4461d4'
    try:
        reader = _csv.DictReader(_server.io.StringIO(csv_text))
        rows = list(reader)
    except _csv.Error as exc:
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, 'csv parse error: {0}'.format(exc))
    if not rows:
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, 'csv is empty')
    fieldnames = [str(n or '').strip().lower() for n in reader.fieldnames or []]
    if 'id' not in fieldnames and 'concept_en' not in fieldnames:
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, 'csv must have an id or concept_en column')
    concepts_path = _server._project_root() / 'concepts.csv'
    project_concepts: _server.List[_server.Dict[str, str]] = []
    if concepts_path.exists():
        with open(concepts_path, newline='', encoding='utf-8') as f:
            project_concepts = list(_csv.DictReader(f))
    by_id: _server.Dict[str, str] = {}
    by_label: _server.Dict[str, str] = {}
    for c in project_concepts:
        cid = _server._normalize_concept_id(c.get('id'))
        lbl = str(c.get('concept_en') or '').strip()
        if cid:
            by_id[cid] = lbl
        if lbl:
            by_label[lbl.casefold()] = cid
    matched_ids: _server.List[str] = []
    missed_labels: _server.List[str] = []
    seen_ids: set = set()
    for row in rows:
        row_id = _server._normalize_concept_id(row.get('id'))
        row_label = str(row.get('concept_en') or '').strip()
        cid = ''
        if row_id and row_id in by_id:
            cid = row_id
        elif row_label and row_label.casefold() in by_label:
            cid = by_label[row_label.casefold()]
        if cid:
            if cid not in seen_ids:
                matched_ids.append(cid)
                seen_ids.add(cid)
        else:
            missed_labels.append(row_label or row_id or '')
    if not matched_ids:
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, 'No rows matched any existing concept by id or concept_en. Import concepts first.')
    tag_id = _re.sub('[^a-z0-9]+', '-', tag_name.lower()).strip('-') or 'tag'
    tags_path = _server._project_root() / 'parse-tags.json'
    existing_tags: _server.List[_server.Dict[str, _server.Any]] = []
    if tags_path.exists():
        try:
            with open(tags_path, 'r', encoding='utf-8') as f:
                raw = _server.json.load(f)
            if isinstance(raw, list):
                existing_tags = raw
        except (OSError, ValueError):
            existing_tags = []
    found = False
    for tag in existing_tags:
        if isinstance(tag, dict) and str(tag.get('id')) == tag_id:
            prev = set(tag.get('concepts') or [])
            prev.update(matched_ids)
            tag['concepts'] = sorted(prev, key=_server._concept_sort_key)
            tag['label'] = tag_name
            tag['color'] = color
            found = True
            break
    if not found:
        existing_tags.append({'id': tag_id, 'label': tag_name, 'color': color, 'concepts': sorted(set(matched_ids), key=_server._concept_sort_key)})
    with open(tags_path, 'w', encoding='utf-8') as f:
        _server.json.dump(existing_tags, f, indent=2, ensure_ascii=False)
    self._send_json(_server.HTTPStatus.OK, {'ok': True, 'tagId': tag_id, 'tagName': tag_name, 'color': color, 'matchedCount': len(matched_ids), 'missedCount': len(missed_labels), 'missedLabels': missed_labels[:50], 'totalTagsInFile': len(existing_tags)})

__all__ = ['_api_get_export_lingpy', '_api_get_export_nexus', '_api_post_concepts_import', '_api_post_tags_import']

