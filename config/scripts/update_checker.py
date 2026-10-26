#!/usr/bin/env python3
"""
Energy Manager Update Checker v1.3.0
"""
import json
import logging
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import PurePosixPath
from marketplace_manager import validate_components

REPOSITORY = os.environ.get('EM_UPDATE_REPOSITORY', 'saltpool/ha-energymanager')
VERSION_RE = re.compile(r'^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$')


def version_tuple(value):
    value = str(value).strip()
    match = VERSION_RE.fullmatch(value)
    if not match:
        raise ValueError(f'Invalid release version: {value!r}; expected major.minor.patch')
    return tuple(int(part) for part in match.groups())


def safe_repo_path(path):
    if not isinstance(path, str) or not path or '\\' in path:
        raise ValueError(f'Invalid repository path: {path!r}')
    if path.startswith('/share/'):
        path = path[1:]
    p = PurePosixPath(path)
    if p.is_absolute() or any(part in ('', '.', '..') for part in path.split('/')) or ':' in path:
        raise ValueError(f'Unsafe repository path: {path!r}')
    return path


def manifest_source_path(path):
    """Map a Home Assistant destination (or flow source) to the repo layout."""
    path = safe_repo_path(path)
    if path.startswith('share/') or path.startswith('nodered/'):
        return path
    return 'config/' + path


class EnergyManagerUpdateChecker:
    def __init__(self, config_dir='/config', branch=None, repository=None):
        self.config_dir = config_dir
        self.em_dir = os.path.join(config_dir, '.energy_manager')
        self.version_file = os.path.join(self.em_dir, 'version.txt')
        self.repository = repository or REPOSITORY
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', self.repository):
            raise ValueError('Invalid GitHub repository')
        self.branch = self.resolve_branch(branch)
        self.logger = logging.getLogger(__name__)
        self.last_error = ''
        self.target_sha = None

    def resolve_branch(self, branch):
        if branch is None:
            token = os.environ.get('SUPERVISOR_TOKEN', '')
            if not token:
                raise RuntimeError(
                    'Cannot read input_select.em_update_branch: '
                    'SUPERVISOR_TOKEN is unavailable. '
                    'Pass --branch explicitly in this environment.'
                )

            request = urllib.request.Request(
                'http://supervisor/core/api/states/input_select.em_update_branch',
                headers={
                    'Authorization': 'Bearer ' + token,
                    'Content-Type': 'application/json',
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    entity = json.loads(response.read())
                branch = entity.get('state')
            except (OSError, ValueError, urllib.error.URLError) as exc:
                raise RuntimeError(
                    'Cannot read input_select.em_update_branch: ' + str(exc)
                ) from exc

        branch = str(branch or '').strip().lower()
        if branch not in ('main', 'early', 'test', 'development'):
            raise ValueError(f'Invalid update branch: {branch!r}')
        return branch

    def _url(self, path, ref=None):
        path = safe_repo_path(path)
        ref = ref or self.target_sha or self.branch
        return ('https://raw.githubusercontent.com/' + self.repository + '/' +
                urllib.parse.quote(ref, safe='') + '/' +
                urllib.parse.quote(path, safe='/'))

    def _read(self, url):
        request = urllib.request.Request(url, headers={'User-Agent': 'EnergyManager-Updater'})
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read()

    def pin_branch(self):
        """Use one commit for metadata and payload so a moving branch cannot mix releases."""
        url = ('https://api.github.com/repos/' + self.repository + '/commits/' + self.branch)
        data = json.loads(self._read(url))
        sha = data.get('sha', '')
        if not re.fullmatch(r'[a-fA-F0-9]{40}', sha):
            raise ValueError('Invalid commit SHA returned by GitHub')
        self.target_sha = sha
        return sha

    def get_current_version(self):
        with open(self.version_file, encoding='utf-8') as file:
            value = file.read().strip()
        version_tuple(value)
        return value

    def set_current_version(self, version):
        version_tuple(version)
        os.makedirs(self.em_dir, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.em_dir, prefix='.version-')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as file:
                file.write(version + '\n')
            os.replace(tmp, self.version_file)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def get_remote_version(self):
        value = self._read(self._url('latest.txt')).decode('utf-8').strip()
        version_tuple(value)
        return value

    def get_update_manifest(self, target_version=None):
        data = json.loads(self._read(self._url('manifest/manifest.json')))
        if not isinstance(data, dict) or not isinstance(data.get('files'), dict):
            raise ValueError('Invalid update manifest')
        if data.get('version') != target_version:
            raise ValueError('Manifest version does not match latest.txt')
        for path, info in data['files'].items():
            manifest_source_path(path)
            if not isinstance(info, dict) or info.get('action', 'merge') not in ('merge', 'replace', 'create'):
                raise ValueError(f'Invalid manifest entry for {path!r}')
            version_tuple(info.get('new_in_version', ''))
        flows = data.get('nodered_flows')
        if flows:
            manifest_source_path(flows['download_url'])
            version_tuple(flows['new_in_version'])
        validate_components(data.get('marketplace_components', []))
        return data

    def check_for_updates(self, force=False):
        result = {'current_version': None, 'remote_version': None,
                  'update_available': False, 'manifest': None,
                  'branch': self.branch, 'commit': None, 'error': ''}
        try:
            result['current_version'] = self.get_current_version()
            result['commit'] = self.pin_branch()
            result['remote_version'] = self.get_remote_version()
            result['manifest'] = self.get_update_manifest(
                result['remote_version']
            )

            if force or version_tuple(result['remote_version']) > version_tuple(result['current_version']):
                result['update_available'] = True
        except (OSError, ValueError, KeyError, urllib.error.URLError) as exc:
            result['error'] = str(exc)
            self.logger.error('Update check failed: %s', exc)
        return result

    def check_for_updates_force(self):
        return self.check_for_updates(force=True)

    def download_file(self, remote_path, local_path):
        try:
            payload = self._read(self._url(manifest_source_path(remote_path)))
            if not payload:
                raise ValueError(f'Empty GitHub file: {remote_path}')
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            fd, temp = tempfile.mkstemp(dir=os.path.dirname(local_path), prefix='.em-download-')
            try:
                with os.fdopen(fd, 'wb') as file:
                    file.write(payload)
                os.replace(temp, local_path)
            finally:
                if os.path.exists(temp):
                    os.unlink(temp)
            return True
        except (OSError, ValueError, urllib.error.URLError) as exc:
            self.logger.error('Failed to download %s: %s', remote_path, exc)
            return False
