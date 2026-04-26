"""PARSE server route-domain module: config."""
from __future__ import annotations

import server as _server

def _workspace_frontend_config(base_config: _server.Optional[_server.Dict[str, _server.Any]]=None) -> _server.Dict[str, _server.Any]:
    config = _server.copy.deepcopy(base_config) if isinstance(base_config, dict) else {}
    project_payload = _server._read_json_file(_server._project_json_path(), {})
    if not isinstance(project_payload, dict):
        project_payload = {}
    source_index_payload = _server._read_json_file(_server._source_index_path(), {})
    if not isinstance(source_index_payload, dict):
        source_index_payload = {}
    speakers: _server.List[str] = []
    speakers_value = project_payload.get('speakers')
    if isinstance(speakers_value, dict):
        speakers.extend((str(key).strip() for key in speakers_value.keys() if str(key).strip()))
    elif isinstance(speakers_value, list):
        speakers.extend((str(item).strip() for item in speakers_value if str(item).strip()))
    source_speakers = source_index_payload.get('speakers')
    if isinstance(source_speakers, dict):
        speakers.extend((str(key).strip() for key in source_speakers.keys() if str(key).strip()))
    speakers = sorted(dict.fromkeys(speakers))
    concepts_path = _server._project_root() / 'concepts.csv'
    concepts: list = []
    if concepts_path.exists():
        import csv as _csv
        with open(concepts_path, newline='', encoding='utf-8') as f:
            reader = _csv.DictReader(f)
            for row in reader:
                cid = str(row.get('id') or '').strip()
                label = str(row.get('concept_en') or '').strip()
                if not (cid and label):
                    continue
                entry: _server.Dict[str, _server.Any] = {'id': cid, 'label': label}
                survey_item = str(row.get('survey_item') or '').strip()
                if survey_item:
                    entry['survey_item'] = survey_item
                custom_order_raw = str(row.get('custom_order') or '').strip()
                if custom_order_raw:
                    try:
                        entry['custom_order'] = int(custom_order_raw)
                    except ValueError:
                        try:
                            entry['custom_order'] = float(custom_order_raw)
                        except ValueError:
                            pass
                concepts.append(entry)
    language_block = project_payload.get('language') if isinstance(project_payload.get('language'), dict) else {}
    language_code = str(project_payload.get('language_code') or language_block.get('code') or config.get('language_code') or 'und').strip() or 'und'
    project_name = str(project_payload.get('project_name') or project_payload.get('name') or config.get('project_name') or 'PARSE').strip() or 'PARSE'
    config['project_name'] = project_name
    config['language_code'] = language_code
    config['speakers'] = speakers
    config['concepts'] = concepts
    config['audio_dir'] = str(project_payload.get('audio_dir') or config.get('audio_dir') or 'audio')
    config['annotations_dir'] = str(project_payload.get('annotations_dir') or config.get('annotations_dir') or 'annotations')
    config['schema_version'] = _server.CONFIG_SCHEMA_VERSION
    return config

def _api_get_config(self) -> None:
    config = _server._workspace_frontend_config(_server.load_ai_config(_server._config_path()))
    self._send_json(_server.HTTPStatus.OK, {'config': config})

def _api_update_config(self) -> None:
    body = self._expect_object(self._read_json_body(), 'Request body')
    current = _server.load_ai_config(_server._config_path())
    merged = _server._deep_merge_dicts(current, body)
    _server._write_json_file(_server._config_path(), merged)
    self._send_json(_server.HTTPStatus.OK, {'success': True, 'config': merged})

def _api_auth_key(self) -> None:
    """POST /api/auth/key — store a direct API key."""
    try:
        data = self._read_json_body()
        key = str(data.get('key') or '').strip()
        provider = str(data.get('provider') or 'xai').strip()
        if not key:
            self._send_json(_server.HTTPStatus.BAD_REQUEST, {'error': 'key is required'})
            return
        from ai.openai_auth import save_api_key, get_auth_status
        save_api_key(key, provider)
        _server._reset_chat_runtime_after_auth_key_save()
        status = get_auth_status()
        self._send_json(_server.HTTPStatus.OK, status)
    except Exception as exc:
        self._send_json(_server.HTTPStatus.INTERNAL_SERVER_ERROR, {'error': str(exc)})

def _api_auth_status(self) -> None:
    from ai.openai_auth import get_auth_status
    self._send_json(_server.HTTPStatus.OK, get_auth_status())

def _api_auth_start(self) -> None:
    from ai.openai_auth import start_device_auth
    try:
        result = start_device_auth()
        self._send_json(_server.HTTPStatus.OK, result)
    except RuntimeError as e:
        self._send_json(_server.HTTPStatus.INTERNAL_SERVER_ERROR, {'error': str(e)})

def _api_auth_poll(self) -> None:
    from ai.openai_auth import poll_device_auth
    result = poll_device_auth()
    self._send_json(_server.HTTPStatus.OK, result)

def _api_auth_logout(self) -> None:
    from ai.openai_auth import clear_tokens
    clear_tokens()
    self._send_json(_server.HTTPStatus.OK, {'success': True})

__all__ = ['_workspace_frontend_config', '_api_get_config', '_api_update_config', '_api_auth_key', '_api_auth_status', '_api_auth_start', '_api_auth_poll', '_api_auth_logout']

